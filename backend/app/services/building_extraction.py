"""Local-only zero-shot building footprint extraction with Grounding DINO + SAM.

Models must be present in the Hugging Face cache before inference. This module
does not download weights, call a hosted inference API, or train a model.
"""
from functools import lru_cache
import logging
from typing import Any

import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union

from app.config import get_settings
from app.geo.crs import transform_geometry
from app.geo.geometry_utils import area_sqm, centroid_latlon

logger = logging.getLogger("services.building_extraction")


class BuildingModelUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _load_models():
    settings = get_settings()
    try:
        import torch
        from transformers import (
            AutoModelForZeroShotObjectDetection, AutoProcessor, SamModel, SamProcessor,
        )
    except ImportError as error:
        raise BuildingModelUnavailable(
            "Building extraction needs the optional local AI dependencies in backend/requirements-ai.txt."
        ) from error

    try:
        device = "cuda" if torch.cuda.is_available() else (
            "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
        )
        detector_processor = AutoProcessor.from_pretrained(
            settings.BUILDING_DETECTOR_MODEL, local_files_only=True
        )
        detector = AutoModelForZeroShotObjectDetection.from_pretrained(
            settings.BUILDING_DETECTOR_MODEL, local_files_only=True
        ).to(device).eval()
        segmenter_processor = SamProcessor.from_pretrained(
            settings.BUILDING_SEGMENTER_MODEL, local_files_only=True
        )
        segmenter = SamModel.from_pretrained(
            settings.BUILDING_SEGMENTER_MODEL, local_files_only=True
        ).to(device).eval()
    except Exception as error:
        raise BuildingModelUnavailable(
            "Local building models are not cached. Run the documented free model download command first."
        ) from error
    return torch, device, detector_processor, detector, segmenter_processor, segmenter


def _to_rgb_uint8(bands: np.ndarray) -> np.ndarray:
    """Convert one or three raster bands to an 8-bit display image for inference."""
    if bands.shape[0] == 1:
        bands = np.repeat(bands, 3, axis=0)
    rgb = np.empty((bands.shape[1], bands.shape[2], 3), dtype=np.uint8)
    for index in range(3):
        band = np.asarray(bands[index], dtype=np.float32)
        finite = np.isfinite(band)
        if not finite.any():
            rgb[:, :, index] = 0
            continue
        low, high = np.percentile(band[finite], (2, 98))
        if high <= low:
            high = low + 1
        scaled = np.clip((band - low) * (255.0 / (high - low)), 0, 255)
        scaled[~finite] = 0
        rgb[:, :, index] = scaled.astype(np.uint8)
    return rgb


def _mask_to_polygon(mask: np.ndarray, affine: Any):
    from rasterio.features import shapes

    pieces = [shape(geometry) for geometry, value in shapes(
        mask.astype(np.uint8), mask=mask.astype(bool), transform=affine
    ) if value == 1]
    polygons = [piece for piece in pieces if piece.geom_type in ("Polygon", "MultiPolygon") and not piece.is_empty]
    return unary_union(polygons) if polygons else None


def _is_duplicate(candidate, existing, threshold: float = 0.82) -> bool:
    for previous in existing:
        try:
            intersection = candidate.intersection(previous).area
            union = candidate.union(previous).area
            if union and intersection / union >= threshold:
                return True
        except Exception:
            continue
    return False


def extract_buildings_from_raster(path: str) -> list[dict[str, Any]]:
    """Infer building polygons from a georeferenced RGB raster, locally and by tile."""
    settings = get_settings()
    if not settings.BUILDING_EXTRACTION_ENABLED:
        return []
    import rasterio
    from rasterio.windows import Window
    from PIL import Image

    torch, device, detector_processor, detector, sam_processor, segmenter = _load_models()
    tile_size = max(256, min(settings.BUILDING_TILE_SIZE, 1536))
    overlap = max(0, min(settings.BUILDING_TILE_OVERLAP, tile_size // 4))
    step = tile_size - overlap
    accepted = []
    with rasterio.open(path) as source:
        if not source.crs:
            raise ValueError("Building extraction requires a georeferenced raster CRS")
        if source.count >= 3:
            band_indexes = (1, 2, 3)
        else:
            band_indexes = (1,)
        for top in range(0, source.height, step):
            for left in range(0, source.width, step):
                height = min(tile_size, source.height - top)
                width = min(tile_size, source.width - left)
                window = Window(left, top, width, height)
                rgb = _to_rgb_uint8(source.read(band_indexes, window=window))
                image = Image.fromarray(rgb, mode="RGB")

                detector_inputs = detector_processor(
                    images=image, text="building.", return_tensors="pt"
                ).to(device)
                with torch.inference_mode():
                    detections = detector(**detector_inputs)
                detected = detector_processor.post_process_grounded_object_detection(
                    detections,
                    detector_inputs.input_ids,
                    threshold=settings.BUILDING_DETECTION_THRESHOLD,
                    text_threshold=settings.BUILDING_DETECTION_THRESHOLD,
                    target_sizes=[(height, width)],
                )[0]

                boxes = detected["boxes"][:40].tolist()
                scores = detected["scores"][:40].tolist()
                for box, score in zip(boxes, scores):
                    box = [
                        max(0.0, min(float(width), float(box[0]))),
                        max(0.0, min(float(height), float(box[1]))),
                        max(0.0, min(float(width), float(box[2]))),
                        max(0.0, min(float(height), float(box[3]))),
                    ]
                    if box[2] <= box[0] or box[3] <= box[1]:
                        continue
                    sam_inputs = sam_processor(
                        image, input_boxes=[[[box]]], return_tensors="pt"
                    ).to(device)
                    with torch.inference_mode():
                        segmented = segmenter(**sam_inputs, multimask_output=False)
                    masks = sam_processor.image_processor.post_process_masks(
                        segmented.pred_masks.cpu(), sam_inputs["original_sizes"].cpu()
                    )
                    mask = masks[0][0][0].numpy().astype(bool)
                    if int(mask.sum()) < 9:
                        continue
                    polygon = _mask_to_polygon(mask, source.window_transform(window))
                    if polygon is None or polygon.is_empty:
                        continue
                    polygon, _ = transform_geometry(polygon, str(source.crs), settings.TARGET_CRS)
                    if not polygon.is_valid:
                        polygon = polygon.buffer(0)
                    if polygon.is_empty or _is_duplicate(polygon, [item["geometry"] for item in accepted]):
                        continue
                    lat, lon = centroid_latlon(polygon)
                    accepted.append({
                        "geometry": polygon,
                        "area_sqm": area_sqm(polygon, settings.TARGET_CRS),
                        "centroid_lat": lat,
                        "centroid_lon": lon,
                        "confidence": round(float(score) * 100, 1),
                    })
    logger.info("Local building inference produced %s reviewable footprints", len(accepted))
    return accepted
