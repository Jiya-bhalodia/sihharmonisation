"""Readiness checks for a defensible, single-area land-record pilot.

The check is intentionally conservative: it reports evidence available in the
uploaded data and never labels a pilot "ready" merely because a similarly
named file exists.  Departmental approval and legal authority still require a
human decision outside the application.
"""
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.orm import Dataset, Feature
from app.sample_data import get_sample_data_dir


PARCEL_ID_FIELDS = {"parcel_id", "survey_no", "survey_number", "gat_no", "survey_gat_no", "cts_no", "plot_no"}
ACCURACY_FIELDS = {"horizontal_accuracy_m", "horizontal_accuracy", "accuracy_m", "accuracy"}


def _fields(features: Iterable[Feature]) -> set[str]:
    return {
        str(key).strip().lower()
        for feature in features
        for key in (feature.raw_properties or {}).keys()
    }


def _check(check_id: str, required: bool, passed: bool, title: str, detail: str, action: str,
           limitation: bool = False) -> dict[str, Any]:
    return {
        "id": check_id,
        "required": required,
        "status": "PASS" if passed else ("LIMITATION" if limitation else ("BLOCKER" if required else "RECOMMENDED")),
        "title": title,
        "detail": detail,
        "action": action,
    }


def evaluate_pilot_readiness(datasets: Iterable[Dataset], features_by_dataset: dict[str, list[Feature]], aoi_exists: bool,
                             free_demo_mode: bool = False) -> dict[str, Any]:
    """Return a transparent readiness report from uploaded pilot data."""
    grouped: dict[str, list[Dataset]] = defaultdict(list)
    for dataset in datasets:
        grouped[dataset.source_type].append(dataset)

    cadastral = grouped["cadastral"]
    cadastral_fields = _fields(feature for item in cadastral for feature in features_by_dataset.get(item.id, []))
    cadastral_ok = bool(cadastral) and bool(cadastral_fields & PARCEL_ID_FIELDS)

    revenue = grouped["revenue"]
    revenue_fields = _fields(feature for item in revenue for feature in features_by_dataset.get(item.id, []))
    revenue_ok = bool(revenue) and bool(revenue_fields & PARCEL_ID_FIELDS)

    gnss = grouped["gnss"]
    gnss_features = [feature for item in gnss for feature in features_by_dataset.get(item.id, [])]
    gnss_fields = _fields(gnss_features)
    gnss_ok = len(gnss_features) >= 10 and bool(gnss_fields & ACCURACY_FIELDS)

    imagery = grouped["orthoimagery"] + grouped["drone"]
    raster_features = [feature for item in imagery for feature in features_by_dataset.get(item.id, [])]
    pixel_sizes = []
    for feature in raster_features:
        pixel_size = (feature.raw_properties or {}).get("pixel_size")
        if isinstance(pixel_size, list) and pixel_size:
            try:
                pixel_sizes.append(max(float(value) for value in pixel_size))
            except (TypeError, ValueError):
                pass
    imagery_ok = bool(pixel_sizes) and min(pixel_sizes) <= 0.20

    aoi_detail = (
        "A bounded synthetic AOI fixture is present for the hosted demo sample area; hosted vector workflows do not clip data to it."
        if free_demo_mode and aoi_exists else
        "Hosted vector workflows do not require an AOI; production pilot clipping and area-wide assessment are not demonstrated."
        if free_demo_mode else
        "An AOI file is required so every departmental layer is clipped and assessed against the same boundary."
    )
    aoi_action = (
        "Treat this synthetic boundary as demo-only; provide an approved AOI for production pilot assessment."
        if free_demo_mode else
        "Create data/raw/pilot/aoi.geojson in EPSG:4326; do not invent an AOI from the building layer."
    )
    checks = [
        _check("aoi", not free_demo_mode, aoi_exists, "Common area of interest", aoi_detail, aoi_action,
               limitation=free_demo_mode and not aoi_exists),
        _check("cadastral", True, cadastral_ok, "Cadastral demo fixture" if free_demo_mode else "Authoritative cadastral parcels", f"{len(cadastral)} synthetic demo cadastral dataset(s); parcel-key fields detected: {', '.join(sorted(cadastral_fields & PARCEL_ID_FIELDS)) or 'none'}." if free_demo_mode else f"{len(cadastral)} cadastral dataset(s); parcel-key fields detected: {', '.join(sorted(cadastral_fields & PARCEL_ID_FIELDS)) or 'none'}.", "Synthetic fixture only; provide approved parcel polygons for a production pilot." if free_demo_mode else "Upload the approved parcel polygons with CTS, survey, or gat IDs."),
        _check("revenue", True, revenue_ok, "Revenue demo fixture" if free_demo_mode else "Revenue records linked by parcel key", f"{len(revenue)} synthetic demo revenue dataset(s); link-key fields detected: {', '.join(sorted(revenue_fields & PARCEL_ID_FIELDS)) or 'none'}." if free_demo_mode else f"{len(revenue)} revenue dataset(s); link-key fields detected: {', '.join(sorted(revenue_fields & PARCEL_ID_FIELDS)) or 'none'}.", "Synthetic fixture only; provide approved revenue data for a production pilot." if free_demo_mode else "Use the same CTS/survey/gat key as the cadastral layer; mask personal data for demonstrations."),
        _check("municipal", True, bool(grouped["municipal"]), "Municipal demo fixture" if free_demo_mode else "Municipal building layer", f"{len(grouped['municipal'])} synthetic demo municipal dataset(s) uploaded." if free_demo_mode else f"{len(grouped['municipal'])} municipal dataset(s) uploaded.", "Synthetic fixture only; provide an approved building layer for a production pilot." if free_demo_mode else "Upload building footprints with source and capture date."),
        _check("gnss", True, gnss_ok, f"Synthetic GNSS demo observations ({len(gnss_features)} points)" if free_demo_mode else f"GNSS / field verification ({len(gnss_features)} points)", f"Synthetic demo points; accuracy fields detected: {', '.join(sorted(gnss_fields & ACCURACY_FIELDS)) or 'none'}. These are not official SOI CORS observations." if free_demo_mode else f"Accuracy fields detected: {', '.join(sorted(gnss_fields & ACCURACY_FIELDS)) or 'none'}. Minimum: 10 points with recorded accuracy.", "Synthetic fixture only; provide approved field observations for a production pilot." if free_demo_mode else "Upload 10–20 points with survey date, method, and horizontal accuracy."),
        _check("imagery", not free_demo_mode, imagery_ok, "High-resolution drone / ORI", "No verified <=20 cm raster was found." if not imagery_ok else f"Best detected raster pixel size: {min(pixel_sizes):.3f} m.", "Upload an authorised drone/ORI GeoTIFF/COG with CRS and capture metadata. Sentinel/Copernicus data is not sufficient for footprint extraction.", limitation=free_demo_mode and not imagery_ok),
        _check("utilities", False, bool(grouped["utility"]), "Authoritative utility network", f"{len(grouped['utility'])} utility dataset(s) uploaded.", "Obtain a water, sewer, or electricity layer from its responsible utility authority."),
        _check("terrain", False, bool(grouped["dsm"] or grouped["dtm"]), "DSM / DTM", f"{len(grouped['dsm'])} DSM and {len(grouped['dtm'])} DTM dataset(s) uploaded.", "Add a survey-grade DSM/DTM with vertical datum before height-based analysis."),
    ]
    blockers = sum(check["status"] == "BLOCKER" for check in checks)
    return {
        "status": ("DEMO_READY" if free_demo_mode else "READY_FOR_REVIEW") if blockers == 0 else "NOT_READY",
        "blocker_count": blockers,
        "checks": checks,
        "limitations": (["Raster processing and high-resolution imagery checks are disabled in the hosted evaluation profile.",
                         "Synthetic demo data cannot establish production pilot readiness."]
                        + (["AOI-based clipping is not part of the hosted vector demo workflow."] if free_demo_mode else [])),
        "disclaimer": "This automated check verifies technical evidence only. It does not certify legal title, source authority, or departmental approval.",
    }


def get_pilot_readiness(db: Session, free_demo_mode: bool = False) -> dict[str, Any]:
    datasets = db.query(Dataset).all()
    features_by_dataset = {
        dataset.id: db.query(Feature).filter(Feature.dataset_id == dataset.id).all()
        for dataset in datasets
    }
    project_root = Path(__file__).resolve().parents[3]
    if free_demo_mode:
        try:
            aoi_exists = (get_sample_data_dir() / "hosted_demo_aoi.geojson").is_file()
        except FileNotFoundError:
            aoi_exists = False
    else:
        aoi_path = project_root / "data" / "raw" / "pilot" / "aoi.geojson"
        aoi_exists = aoi_path.is_file()
    return evaluate_pilot_readiness(datasets, features_by_dataset, aoi_exists, free_demo_mode)
