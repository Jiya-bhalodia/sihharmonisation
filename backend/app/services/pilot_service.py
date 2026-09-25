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


PARCEL_ID_FIELDS = {"parcel_id", "survey_no", "survey_number", "gat_no", "survey_gat_no", "cts_no", "plot_no"}
ACCURACY_FIELDS = {"horizontal_accuracy_m", "horizontal_accuracy", "accuracy_m", "accuracy"}


def _fields(features: Iterable[Feature]) -> set[str]:
    return {
        str(key).strip().lower()
        for feature in features
        for key in (feature.raw_properties or {}).keys()
    }


def _check(check_id: str, required: bool, passed: bool, title: str, detail: str, action: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "required": required,
        "status": "PASS" if passed else ("BLOCKER" if required else "RECOMMENDED"),
        "title": title,
        "detail": detail,
        "action": action,
    }


def evaluate_pilot_readiness(datasets: Iterable[Dataset], features_by_dataset: dict[str, list[Feature]], aoi_exists: bool) -> dict[str, Any]:
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

    checks = [
        _check("aoi", True, aoi_exists, "Common area of interest", "An AOI file is required so every departmental layer is clipped and assessed against the same boundary.", "Create data/raw/pilot/aoi.geojson in EPSG:4326; do not invent an AOI from the building layer."),
        _check("cadastral", True, cadastral_ok, "Authoritative cadastral parcels", f"{len(cadastral)} cadastral dataset(s); parcel-key fields detected: {', '.join(sorted(cadastral_fields & PARCEL_ID_FIELDS)) or 'none'}.", "Upload the approved parcel polygons with CTS, survey, or gat IDs."),
        _check("revenue", True, revenue_ok, "Revenue records linked by parcel key", f"{len(revenue)} revenue dataset(s); link-key fields detected: {', '.join(sorted(revenue_fields & PARCEL_ID_FIELDS)) or 'none'}.", "Use the same CTS/survey/gat key as the cadastral layer; mask personal data for demonstrations."),
        _check("municipal", True, bool(grouped["municipal"]), "Municipal building layer", f"{len(grouped['municipal'])} municipal dataset(s) uploaded.", "Upload building footprints with source and capture date."),
        _check("gnss", True, gnss_ok, f"GNSS / field verification ({len(gnss_features)} points)", f"Accuracy fields detected: {', '.join(sorted(gnss_fields & ACCURACY_FIELDS)) or 'none'}. Minimum: 10 points with recorded accuracy.", "Upload 10–20 points with survey date, method, and horizontal accuracy."),
        _check("imagery", True, imagery_ok, "High-resolution drone / ORI", "No verified <=20 cm raster was found." if not imagery_ok else f"Best detected raster pixel size: {min(pixel_sizes):.3f} m.", "Upload an authorised drone/ORI GeoTIFF/COG with CRS and capture metadata. Sentinel/Copernicus data is not sufficient for footprint extraction."),
        _check("utilities", False, bool(grouped["utility"]), "Authoritative utility network", f"{len(grouped['utility'])} utility dataset(s) uploaded.", "Obtain a water, sewer, or electricity layer from its responsible utility authority."),
        _check("terrain", False, bool(grouped["dsm"] or grouped["dtm"]), "DSM / DTM", f"{len(grouped['dsm'])} DSM and {len(grouped['dtm'])} DTM dataset(s) uploaded.", "Add a survey-grade DSM/DTM with vertical datum before height-based analysis."),
    ]
    blockers = sum(check["status"] == "BLOCKER" for check in checks)
    return {
        "status": "READY_FOR_REVIEW" if blockers == 0 else "NOT_READY",
        "blocker_count": blockers,
        "checks": checks,
        "disclaimer": "This automated check verifies technical evidence only. It does not certify legal title, source authority, or departmental approval.",
    }


def get_pilot_readiness(db: Session) -> dict[str, Any]:
    datasets = db.query(Dataset).all()
    features_by_dataset = {
        dataset.id: db.query(Feature).filter(Feature.dataset_id == dataset.id).all()
        for dataset in datasets
    }
    project_root = Path(__file__).resolve().parents[3]
    aoi_exists = (project_root / "data" / "raw" / "pilot" / "aoi.geojson").is_file()
    return evaluate_pilot_readiness(datasets, features_by_dataset, aoi_exists)
