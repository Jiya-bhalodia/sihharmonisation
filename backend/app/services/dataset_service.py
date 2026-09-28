"""
Dataset ingestion service.

Handles GeoJSON / CSV(lat,lon) / Shapefile-ZIP uploads, computes a basic
data quality score, detects the source CRS, and persists Dataset +
Feature rows.

Security fix (senior review): shapefile ZIP extraction previously called
zf.extractall() directly, which is vulnerable to a "zip slip" path
traversal attack (a malicious archive entry named e.g.
"../../etc/passwd" could write outside the intended temp directory).
Every archive member's resolved path is now validated to stay within the
temp extraction directory before anything is extracted.
"""
import os
import json
import zipfile
import tempfile
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.orm import Dataset, Feature
from app.utils.ids import new_id
from app.utils.logger import get_logger
from app.geo.crs import detect_crs, transform_geometry, geometry_to_geojson_str
from app.geo.geometry_utils import area_sqm, centroid_latlon
from app.config import get_settings
from shapely.geometry import shape

logger = get_logger("services.dataset")
settings = get_settings()

CANONICAL_TYPE_BY_SOURCE = {
    "cadastral": "parcel",
    "land_use": "parcel",
    "revenue": "parcel",
    "municipal": "building",
    "gnss": "gnss_point",
    "ground_truth": "ground_truth",
    "utility": "utility",
    "drone": "building",
    "orthoimagery": "raster",
    "dsm": "raster",
    "dtm": "raster",
}


def _compute_quality_score(features: list) -> float:
    """Simple heuristic data quality score: valid geometry ratio + attribute completeness."""
    if not features:
        return 0.0
    valid_count = sum(1 for f in features if f.get("is_valid_geometry", True))
    completeness_scores = []
    for f in features:
        props = f.get("raw_properties", {})
        non_null = sum(1 for v in props.values() if v not in (None, "", "NULL"))
        completeness_scores.append(non_null / max(1, len(props)))
    validity_ratio = valid_count / len(features)
    completeness_ratio = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.5
    return round((0.6 * validity_ratio + 0.4 * completeness_ratio) * 100, 1)


def ingest_geojson_dict(
    db: Session,
    geojson: dict,
    name: str,
    department: str,
    source_type: str,
    declared_crs: Optional[str] = None,
    provenance: str = "user_upload",
) -> Dataset:
    """Core ingestion routine shared by file upload and sample data loading."""
    feats = geojson.get("features", [])
    canonical_type = CANONICAL_TYPE_BY_SOURCE.get(source_type, "parcel")

    sample_coords = None
    if feats:
        try:
            g = shape(feats[0]["geometry"])
            c = g.centroid
            sample_coords = (c.x, c.y)
        except Exception:
            pass

    source_crs = detect_crs(declared_crs or geojson.get("crs_hint"), sample_coords)

    dataset = Dataset(
        id=new_id("DS"),
        name=name,
        department=department,
        source_type=source_type,
        provenance=provenance,
        geometry_type=feats[0]["geometry"]["type"] if feats else "Unknown",
        crs=source_crs,
        feature_count=0,
        quality_score=0.0,
        status="processing",
        uploaded_at=datetime.utcnow(),
    )
    db.add(dataset)
    db.flush()

    prepared_features = []
    for feat in feats:
        try:
            geom = shape(feat["geometry"])
            transformed_geom, tstatus = transform_geometry(geom, source_crs, settings.TARGET_CRS)
            is_valid = transformed_geom.is_valid and not transformed_geom.is_empty
            lat, lon = centroid_latlon(transformed_geom)
            area = area_sqm(transformed_geom, settings.TARGET_CRS) if transformed_geom.geom_type in (
                "Polygon", "MultiPolygon") else None

            props = feat.get("properties", {}) or {}

            f = Feature(
                id=new_id("FT"),
                dataset_id=dataset.id,
                canonical_type=canonical_type,
                raw_properties=props,
                geometry_geojson=geometry_to_geojson_str(transformed_geom),
                centroid_lat=lat,
                centroid_lon=lon,
                area_sqm=area,
                is_valid_geometry=is_valid,
                created_at=datetime.utcnow(),
            )
            db.add(f)
            prepared_features.append({
                "is_valid_geometry": is_valid,
                "raw_properties": props,
            })
        except Exception as e:
            logger.warning(f"Skipping malformed feature in {name}: {e}")
            continue

    dataset.feature_count = len(prepared_features)
    dataset.quality_score = _compute_quality_score(prepared_features)
    dataset.status = "uploaded"
    db.commit()
    db.refresh(dataset)
    logger.info(f"Ingested dataset {dataset.id} ({name}) with {dataset.feature_count} features, quality={dataset.quality_score}")
    return dataset


def ingest_geojson_file(db: Session, file_bytes: bytes, name: str, department: str, source_type: str) -> Dataset:
    try:
        geojson = json.loads(file_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"File is not valid UTF-8 JSON: {e}")
    if not isinstance(geojson, dict) or geojson.get("type") != "FeatureCollection":
        raise ValueError("File must be a GeoJSON FeatureCollection")
    return ingest_geojson_dict(db, geojson, name, department, source_type)


def ingest_csv_latlon(db: Session, file_bytes: bytes, name: str, department: str, source_type: str,
                       lat_field: str = "latitude", lon_field: str = "longitude",
                       provenance: str = "user_upload") -> Dataset:
    import pandas as pd
    import io

    df = pd.read_csv(io.BytesIO(file_bytes))
    features = []
    for _, row in df.iterrows():
        if lat_field not in row or lon_field not in row:
            continue
        try:
            lat, lon = float(row[lat_field]), float(row[lon_field])
        except (ValueError, TypeError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue  # reject out-of-range coordinates rather than silently ingesting garbage
        props = {k: (None if pd.isna(v) else v) for k, v in row.items() if k not in (lat_field, lon_field)}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })
    geojson = {"type": "FeatureCollection", "features": features}
    return ingest_geojson_dict(db, geojson, name, department, source_type,
                               declared_crs="EPSG:4326", provenance=provenance)


def _safe_extract_zip(zf: zipfile.ZipFile, dest_dir: str) -> None:
    """
    Extract a ZIP archive after validating that every member resolves to a
    path INSIDE dest_dir. Prevents a "zip slip" path-traversal attack via
    a crafted member name such as '../../../etc/somefile'.
    """
    dest_dir_resolved = os.path.realpath(dest_dir)
    for member in zf.namelist():
        member_path = os.path.realpath(os.path.join(dest_dir, member))
        if not (member_path == dest_dir_resolved or member_path.startswith(dest_dir_resolved + os.sep)):
            raise ValueError(f"Unsafe path detected in uploaded archive: {member}")
    zf.extractall(dest_dir)


def ingest_shapefile_zip(db: Session, file_bytes: bytes, name: str, department: str, source_type: str) -> Dataset:
    import geopandas as gpd

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "upload.zip")
        with open(zip_path, "wb") as f:
            f.write(file_bytes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extract_zip(zf, tmp)

        shp_file = None
        for root, _, files in os.walk(tmp):
            for fname in files:
                if fname.lower().endswith(".shp"):
                    shp_file = os.path.join(root, fname)
                    break
        if not shp_file:
            raise ValueError("No .shp file found inside uploaded ZIP")

        gdf = gpd.read_file(shp_file)
        declared_crs = str(gdf.crs) if gdf.crs else None
        gdf = gdf.to_crs("EPSG:4326") if gdf.crs else gdf
        geojson = json.loads(gdf.to_json())
        return ingest_geojson_dict(db, geojson, name, department, source_type, declared_crs=declared_crs or "EPSG:4326")


def list_datasets(db: Session):
    return db.query(Dataset).order_by(Dataset.uploaded_at.desc()).all()
