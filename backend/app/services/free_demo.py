"""Strict resource and workflow limits for the hosted evaluation profile."""
import csv
import io
import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.orm import Dataset, Feature

VECTOR_EXTENSIONS = {".csv", ".json", ".geojson"}
VECTOR_HARMONIZATION_JOB = "vector_harmonization"


class FreeDemoTimeLimitExceeded(RuntimeError):
    """Cooperative time budget reached between bounded processing steps."""


def unavailable(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=f"Unavailable in the hosted evaluation demo: {message}")


def require_job_type(job_type: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if job_type != VECTOR_HARMONIZATION_JOB or job_type not in settings.free_demo_allowed_jobs:
        raise unavailable("this processing job is not in the lightweight vector workflow allowlist.")


def check_processing_deadline(deadline: float | None) -> None:
    if deadline is not None:
        import time
        if time.monotonic() > deadline:
            raise FreeDemoTimeLimitExceeded(
                "The job exceeded the configured free-demo processing time budget. "
                "Reduce the dataset size and try again."
            )


def _coordinate_count(value: Any) -> int:
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(item, (int, float)) and not isinstance(item, bool)
                                   for item in value[:2]):
            return 1
        return sum(_coordinate_count(item) for item in value)
    return 0


def _geometry_complexity(geometry: Any) -> int:
    """Count positions in GeoJSON geometry, including nested GeometryCollections."""
    if not isinstance(geometry, dict):
        return 0
    count = _coordinate_count(geometry.get("coordinates"))
    children = geometry.get("geometries", [])
    if isinstance(children, list):
        count += sum(_geometry_complexity(child) for child in children)
    return count


def preflight_upload(filename: str, content: bytes, settings: Settings | None = None) -> tuple[int, int]:
    """Validate file format and bounded feature/vertex counts before DB writes."""
    settings = settings or get_settings()
    suffix = Path(filename).suffix.lower()
    if suffix not in VECTOR_EXTENSIONS:
        raise unavailable("only small CSV and GeoJSON vector files are accepted; rasters, imagery, archives, and PDF/OCR are disabled.")
    if len(content) > settings.FREE_DEMO_MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Free demo uploads are limited to {settings.FREE_DEMO_MAX_UPLOAD_MB} MB.",
        )

    if suffix == ".csv":
        try:
            text = content.decode("utf-8-sig")
            count = max(0, sum(1 for _ in csv.reader(io.StringIO(text))) - 1)
        except (UnicodeDecodeError, csv.Error) as error:
            raise HTTPException(status_code=422, detail="CSV must be valid UTF-8 tabular data.") from error
        complexity = count
    else:
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            raise HTTPException(status_code=422, detail="GeoJSON must be valid UTF-8 JSON.") from error
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise HTTPException(status_code=422, detail="File must be a GeoJSON FeatureCollection.")
        features = payload.get("features")
        if not isinstance(features, list):
            raise HTTPException(status_code=422, detail="GeoJSON FeatureCollection must contain a features array.")
        count = len(features)
        complexity = 0
        for feature in features:
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry")
            if geometry is not None and not isinstance(geometry, dict):
                continue  # the regular parser will report malformed feature geometry
            try:
                complexity += _geometry_complexity(geometry)
            except RecursionError as error:
                raise HTTPException(status_code=413, detail="This geometry exceeds the free demo complexity limit.") from error

    if count > settings.FREE_DEMO_MAX_FEATURES:
        raise HTTPException(
            status_code=413,
            detail=f"Free demo uploads are limited to {settings.FREE_DEMO_MAX_FEATURES} features.",
        )
    if complexity > settings.FREE_DEMO_MAX_GEOMETRY_COMPLEXITY:
        raise HTTPException(
            status_code=413,
            detail="This geometry exceeds the free demo complexity limit.",
        )
    return count, complexity


def ensure_dataset_capacity(db: Session, added_features: int = 0,
                            added_complexity: int = 0,
                            settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if db.query(Dataset).count() >= settings.FREE_DEMO_MAX_DATASETS:
        raise HTTPException(
            status_code=413,
            detail=f"Free demo workspaces are limited to {settings.FREE_DEMO_MAX_DATASETS} datasets.",
        )
    existing_count = db.query(Feature).count()
    if existing_count + added_features > settings.FREE_DEMO_MAX_FEATURES:
        raise HTTPException(
            status_code=413,
            detail=f"Free demo workspaces are limited to {settings.FREE_DEMO_MAX_FEATURES} total features.",
        )
    existing_complexity = 0
    for feature in db.query(Feature.geometry_geojson).all():
        if not feature[0]:
            continue
        try:
            geometry = json.loads(feature[0])
        except (TypeError, json.JSONDecodeError):
            continue
        existing_complexity += _geometry_complexity(geometry)
    if existing_complexity + added_complexity > settings.FREE_DEMO_MAX_GEOMETRY_COMPLEXITY:
        raise HTTPException(status_code=413, detail="This geometry exceeds the free demo complexity limit.")


def ensure_existing_capacity(db: Session, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    features = db.query(Feature).all()
    if len(features) > settings.FREE_DEMO_MAX_FEATURES:
        raise unavailable(f"the workspace exceeds the {settings.FREE_DEMO_MAX_FEATURES}-feature harmonization limit.")
    complexity = 0
    for feature in features:
        if not feature.geometry_geojson:
            continue
        try:
            geometry = json.loads(feature.geometry_geojson)
        except (TypeError, json.JSONDecodeError):
            continue
        complexity += _geometry_complexity(geometry)
        if complexity > settings.FREE_DEMO_MAX_GEOMETRY_COMPLEXITY:
            raise unavailable("the workspace exceeds the geometry complexity limit.")
