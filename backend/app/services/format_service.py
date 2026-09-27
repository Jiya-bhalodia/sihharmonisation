"""Processors for non-tabular land-administration inputs.

These processors intentionally create normal Dataset/Feature records, so every
supported format goes through the same CRS, quality, provenance and
harmonization workflow as a GeoJSON upload.  They do not fabricate parcels:
rasters become an analysed raster-footprint record and PDFs become extracted
document records until a survey/CTS number can be linked to a parcel.
"""
import io
import json
import logging
import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session
from shapely.geometry import box

from app.config import get_settings
from app.models.orm import Dataset, Feature
from app.services.dataset_service import ingest_geojson_dict
from app.geo.crs import geometry_to_geojson_str, transform_geometry
from app.geo.geometry_utils import area_sqm, centroid_latlon
from app.utils.ids import new_id

settings = get_settings()
logger = logging.getLogger("services.format")


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _coordinates(text: str):
    points = []
    for token in (text or "").replace("\n", " ").split():
        values = token.split(",")
        if len(values) >= 2:
            try:
                points.append([float(values[0]), float(values[1])])
            except ValueError:
                continue
    return points


def _kml_to_geojson(path: str) -> Dict[str, Any]:
    """Stream a KML into GeoJSON without loading a full GeoDataFrame.

    Government revenue KMZ files can contain tens of thousands of parcels.
    Streaming Placemarks keeps their original ExtendedData while avoiding an
    expensive GDAL/GeoPandas intermediate representation.
    """
    features = []
    for _, placemark in ET.iterparse(path, events=("end",)):
        if _local_name(placemark) != "Placemark":
            continue
        props: Dict[str, Any] = {}
        for node in placemark.iter():
            local = _local_name(node)
            if local == "SimpleData" and node.attrib.get("name"):
                props[node.attrib["name"]] = (node.text or "").strip()
            elif local == "Data" and node.attrib.get("name"):
                value = next((child.text for child in node if _local_name(child) == "value"), None)
                props[node.attrib["name"]] = (value or "").strip()
            elif local == "name" and node.text and "name" not in props:
                props["name"] = node.text.strip()
        geometry = None
        polygons = [node for node in placemark.iter() if _local_name(node) == "Polygon"]
        if polygons:
            rings = []
            for polygon in polygons:
                coord_node = next((n for n in polygon.iter() if _local_name(n) == "coordinates"), None)
                if coord_node is not None:
                    ring = _coordinates(coord_node.text or "")
                    if len(ring) >= 4:
                        rings.append(ring)
            if len(rings) == 1:
                geometry = {"type": "Polygon", "coordinates": [rings[0]]}
            elif rings:
                geometry = {"type": "MultiPolygon", "coordinates": [[[p for p in ring]] for ring in rings]}
        if geometry is None:
            line = next((n for n in placemark.iter() if _local_name(n) == "LineString"), None)
            point = next((n for n in placemark.iter() if _local_name(n) == "Point"), None)
            coord_node = next((n for n in line.iter() if _local_name(n) == "coordinates"), None) if line is not None else None
            if coord_node is not None:
                coords = _coordinates(coord_node.text or "")
                if len(coords) >= 2:
                    geometry = {"type": "LineString", "coordinates": coords}
            elif point is not None:
                coord_node = next((n for n in point.iter() if _local_name(n) == "coordinates"), None)
                coords = _coordinates(coord_node.text or "") if coord_node is not None else []
                if coords:
                    geometry = {"type": "Point", "coordinates": coords[0]}
        if geometry is not None:
            features.append({"type": "Feature", "properties": props, "geometry": geometry})
        placemark.clear()
    if not features:
        raise ValueError("No supported Point, LineString, or Polygon features found in KML/KMZ")
    return {"type": "FeatureCollection", "features": features}


def ingest_kml_or_kmz(db: Session, file_bytes: bytes, filename: str, name: str,
                      department: str, source_type: str) -> Dataset:
    """Read a real KML/KMZ with GeoPandas/GDAL and reuse GeoJSON ingestion."""
    import geopandas as gpd

    suffix = ".kmz" if filename.lower().endswith(".kmz") else ".kml"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"upload{suffix}")
        with open(path, "wb") as handle:
            handle.write(file_bytes)
        if suffix == ".kmz":
            with zipfile.ZipFile(path) as archive:
                kmls = [n for n in archive.namelist() if n.lower().endswith(".kml")]
                if not kmls:
                    raise ValueError("KMZ does not contain a KML document")
                kml_path = os.path.join(tmp, "document.kml")
                with open(kml_path, "wb") as handle:
                    handle.write(archive.read(kmls[0]))
                path = kml_path
        # KML coordinates are specified in WGS84.  Keep this path independent
        # of optional GDAL KML-driver availability.
        return ingest_geojson_dict(db, _kml_to_geojson(path), name, department,
                                   source_type, declared_crs="EPSG:4326")


def ingest_raster(db: Session, file_bytes: bytes, name: str, department: str,
                  source_type: str, dataset_id: str | None = None,
                  file_path: str | None = None) -> Dataset:
    """Inspect a GeoTIFF/COG and store its true footprint plus useful metadata."""
    import numpy as np
    import rasterio
    from rasterio.io import MemoryFile
    from contextlib import ExitStack

    with ExitStack() as stack:
        if file_path:
            src = stack.enter_context(rasterio.open(file_path))
        else:
            memfile = stack.enter_context(MemoryFile(file_bytes))
            src = stack.enter_context(memfile.open())
        if not src.crs:
            raise ValueError("GeoTIFF has no CRS; add a valid CRS before upload")
        bounds = src.bounds
        footprint = box(bounds.left, bounds.bottom, bounds.right, bounds.top)
        geom, _ = transform_geometry(footprint, str(src.crs), settings.TARGET_CRS)
        # A downsampled first band gives actual input statistics without
        # loading a potentially multi-gigabyte raster into memory.
        sample = src.read(1, out_shape=(1, min(src.height, 512), min(src.width, 512)), masked=True)
        valid = sample.compressed()
        metadata: Dict[str, Any] = {
            "format": "GeoTIFF/COG", "crs": str(src.crs), "width_px": src.width,
            "height_px": src.height, "band_count": src.count,
            "pixel_size": [abs(src.transform.a), abs(src.transform.e)],
            "bounds_source_crs": [bounds.left, bounds.bottom, bounds.right, bounds.top],
            "nodata": src.nodata,
            "sample_valid_pixels": int(valid.size),
            "sample_min": float(np.min(valid)) if valid.size else None,
            "sample_max": float(np.max(valid)) if valid.size else None,
            "sample_mean": round(float(np.mean(valid)), 4) if valid.size else None,
            "acquisition_hint": src.tags().get("TIFFTAG_DATETIME") or src.tags().get("DATE_ACQUIRED"),
            "tags": src.tags(),
        }

    lat, lon = centroid_latlon(geom)
    detected_buildings = []
    extraction_status = "not_applicable"
    if source_type in {"drone", "orthoimagery"}:
        if not settings.BUILDING_EXTRACTION_ENABLED:
            extraction_status = "disabled"
        else:
            try:
                from app.services.building_extraction import extract_buildings_from_raster
                if file_path:
                    detected_buildings = extract_buildings_from_raster(file_path)
                else:
                    with tempfile.NamedTemporaryFile(suffix=".tif") as raster_file:
                        raster_file.write(file_bytes)
                        raster_file.flush()
                        detected_buildings = extract_buildings_from_raster(raster_file.name)
                extraction_status = "completed" if detected_buildings else "no_detections"
            except Exception as error:
                # The source raster remains ingested even if the optional local
                # model runtime is not installed or its weights are not cached.
                extraction_status = "unavailable"
                metadata["building_extraction_note"] = str(error)[:500]
                logger.warning("Building extraction unavailable for %s: %s", name, error)
        metadata["building_extraction_status"] = extraction_status
        metadata["building_footprint_count"] = len(detected_buildings)
    if dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if dataset is None:
            raise ValueError("Queued raster dataset no longer exists")
        db.query(Feature).filter(Feature.dataset_id == dataset.id).delete()
        dataset.geometry_type = "Raster footprint"
        dataset.crs = str(metadata["crs"])
        dataset.feature_count = 1 + len(detected_buildings)
        dataset.quality_score = 100.0
        dataset.status = "uploaded"
    else:
        dataset = Dataset(id=new_id("DS"), name=name, department=department,
                          source_type=source_type, geometry_type="Raster footprint",
                          crs=str(metadata["crs"]), feature_count=1 + len(detected_buildings), quality_score=100.0,
                          status="uploaded", uploaded_at=datetime.utcnow())
        db.add(dataset)
        db.flush()
    db.add(Feature(id=new_id("FT"), dataset_id=dataset.id, canonical_type="raster",
                   raw_properties=metadata, geometry_geojson=geometry_to_geojson_str(geom),
                   centroid_lat=lat, centroid_lon=lon,
                   area_sqm=area_sqm(geom, settings.TARGET_CRS), is_valid_geometry=geom.is_valid,
                   created_at=datetime.utcnow()))
    for building in detected_buildings:
        building_geometry = building["geometry"]
        db.add(Feature(
            id=new_id("FT"), dataset_id=dataset.id, canonical_type="building",
            raw_properties={
                "extraction_method": "Grounding DINO + SAM (local pretrained models)",
                "detection_confidence": building["confidence"],
                "needs_review": True,
            },
            geometry_geojson=geometry_to_geojson_str(building_geometry),
            centroid_lat=building["centroid_lat"], centroid_lon=building["centroid_lon"],
            area_sqm=building["area_sqm"], is_valid_geometry=building_geometry.is_valid,
            created_at=datetime.utcnow(),
        ))
    db.commit()
    db.refresh(dataset)
    return dataset


def _extract_pdf_fields(text: str) -> Dict[str, Any]:
    """Extract common Indian land-record identifiers, retaining source text for review."""
    fields: Dict[str, Any] = {"document_type": "PDF", "text_preview": text[:3000]}
    patterns = {
        "survey_number": r"(?:survey|gat|cts)\s*(?:no\.?|number)?\s*[:#-]?\s*([A-Za-z0-9/-]+)",
        "khata_number": r"(?:khata)\s*(?:no\.?|number)?\s*[:#-]?\s*([A-Za-z0-9/-]+)",
        "area_text": r"(?:area|क्षेत्र)\s*[:#-]?\s*([0-9.,]+\s*(?:ha|hectare|acre|sq\.?\s*m)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            fields[key] = match.group(1).strip()
    return fields


def ingest_pdf(db: Session, file_bytes: bytes, name: str, department: str,
               source_type: str) -> Dataset:
    """Extract text/identifiers locally; scanned pages use free Tesseract OCR when available."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    extraction_method = "pdf_text_layer"
    ocr_confidence = None
    ocr_pages_processed = 0
    if not text:
        from app.services.ocr_service import OcrUnavailableError, ocr_pdf
        try:
            text, ocr_confidence = ocr_pdf(file_bytes, len(reader.pages))
            extraction_method = "tesseract_ocr"
            ocr_pages_processed = min(len(reader.pages), max(settings.OCR_MAX_PAGES, 1))
        except OcrUnavailableError as error:
            fields = {
                "document_type": "PDF", "ocr_status": "unavailable",
                "review_note": str(error),
            }
        else:
            fields = _extract_pdf_fields(text) if text else {
                "document_type": "PDF", "ocr_status": "no_text_detected",
                "review_note": "OCR ran but did not recover text; inspect the scan manually.",
            }
            fields["ocr_status"] = "completed" if text else "no_text_detected"
            fields["ocr_mean_confidence"] = ocr_confidence
            fields["ocr_pages_processed"] = ocr_pages_processed
            fields["ocr_truncated"] = ocr_pages_processed < len(reader.pages)
    else:
        fields = _extract_pdf_fields(text)
        fields["ocr_status"] = "not_needed"
    fields["extraction_method"] = extraction_method
    fields["page_count"] = len(reader.pages)
    if text:
        fields["text_preview"] = text[:3000]
    dataset = Dataset(id=new_id("DS"), name=name, department=department,
                      source_type=source_type, geometry_type="Document / no geometry",
                      crs=None, feature_count=1, quality_score=70.0, status="uploaded",
                      uploaded_at=datetime.utcnow())
    db.add(dataset)
    db.flush()
    db.add(Feature(id=new_id("FT"), dataset_id=dataset.id, canonical_type="document",
                   raw_properties=fields, geometry_geojson=None, centroid_lat=None,
                   centroid_lon=None, area_sqm=None, is_valid_geometry=True,
                   created_at=datetime.utcnow()))
    db.commit()
    db.refresh(dataset)
    return dataset
