"""
Change detection service.

Compares the CURRENT harmonized dataset snapshot against a PREVIOUS
snapshot (persisted as a simple JSON file per run) to detect new,
removed, modified buildings/parcels, geometry changes, and attribute
changes. In demo mode we snapshot the unified parcel table before each
harmonization run so "before vs after" changes are real, computed diffs.
"""
import os
import json
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.orm import UnifiedParcel, ChangeEvent, Feature, Dataset
from app.utils.ids import new_id
from app.utils.logger import get_logger
from app.config import get_settings

logger = get_logger("services.change")
settings = get_settings()

SNAPSHOT_PATH = os.path.join(settings.DATA_DIR, "generated", "previous_snapshot.json")
VERSION_ID_FIELDS = ("property_id", "parcel_id", "survey_number", "survey_no", "gat_no", "asset_id", "point_id")


def _serialize_parcels(db: Session) -> List[Dict[str, Any]]:
    parcels = db.query(UnifiedParcel).all()
    return [{
        "id": p.id,
        "parcel_id": p.parcel_id,
        "owner_name": p.owner_name,
        "area": p.area,
        "land_use": p.land_use,
        "building_count": p.building_count,
        "geometry_geojson": p.geometry_geojson,
    } for p in parcels]


def save_snapshot(db: Session):
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    data = _serialize_parcels(db)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(data, f)
    logger.info(f"Saved snapshot with {len(data)} parcels to {SNAPSHOT_PATH}")


def load_snapshot() -> List[Dict[str, Any]]:
    if not os.path.exists(SNAPSHOT_PATH):
        return []
    with open(SNAPSHOT_PATH, "r") as f:
        return json.load(f)


def _feature_key(feature: Feature) -> str | None:
    """Return a stable department identifier for source-version comparison."""
    properties = feature.raw_properties or {}
    for field in VERSION_ID_FIELDS:
        value = properties.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"
    return None


def _feature_summary(feature: Feature) -> Dict[str, Any]:
    return {
        "properties": feature.raw_properties or {},
        "geometry_geojson": feature.geometry_geojson,
    }


def _detect_source_version_changes(db: Session, job_id: str) -> int:
    """Compare the two latest uploads of each source type feature-by-feature.

    A parcel-level summary can stay unchanged when, for example, a new building
    footprint is added inside it. This comparison catches those source-level
    additions, removals, attribute edits, and geometry edits using stable IDs.
    """
    datasets = db.query(Dataset).order_by(Dataset.uploaded_at.asc()).all()
    by_type: Dict[str, List[Dataset]] = {}
    for dataset in datasets:
        by_type.setdefault(dataset.source_type, []).append(dataset)

    count = 0
    for source_type, versions in by_type.items():
        if len(versions) < 2:
            continue
        previous_dataset, current_dataset = versions[-2], versions[-1]
        previous = {
            key: feature
            for feature in db.query(Feature).filter(Feature.dataset_id == previous_dataset.id).all()
            if (key := _feature_key(feature))
        }
        current = {
            key: feature
            for feature in db.query(Feature).filter(Feature.dataset_id == current_dataset.id).all()
            if (key := _feature_key(feature))
        }
        # Do not manufacture a comparison for two unrelated layers that
        # happen to share a source type but have no stable common IDs.
        if not previous or not current:
            continue

        for key in sorted(current.keys() - previous.keys()):
            feature = current[key]
            db.add(ChangeEvent(
                id=new_id("CE"), job_id=job_id, feature_ref=feature.id, change_type="new",
                before=None, after=_feature_summary(feature), confidence=100.0,
                detected_at=datetime.utcnow(),
            ))
            count += 1
        for key in sorted(previous.keys() - current.keys()):
            feature = previous[key]
            db.add(ChangeEvent(
                id=new_id("CE"), job_id=job_id, feature_ref=feature.id, change_type="removed",
                before=_feature_summary(feature), after=None, confidence=100.0,
                detected_at=datetime.utcnow(),
            ))
            count += 1
        for key in sorted(current.keys() & previous.keys()):
            before, after = previous[key], current[key]
            if before.geometry_geojson != after.geometry_geojson:
                db.add(ChangeEvent(
                    id=new_id("CE"), job_id=job_id, feature_ref=after.id, change_type="geometry_changed",
                    before={"feature_key": key, "geometry_geojson": before.geometry_geojson},
                    after={"feature_key": key, "geometry_geojson": after.geometry_geojson},
                    confidence=100.0, detected_at=datetime.utcnow(),
                ))
                count += 1
            if (before.raw_properties or {}) != (after.raw_properties or {}):
                db.add(ChangeEvent(
                    id=new_id("CE"), job_id=job_id, feature_ref=after.id, change_type="attribute_changed",
                    before={"feature_key": key, "properties": before.raw_properties or {}},
                    after={"feature_key": key, "properties": after.raw_properties or {}},
                    confidence=100.0, detected_at=datetime.utcnow(),
                ))
                count += 1
    return count


def detect_changes(db: Session, job_id: str) -> int:
    """
    Compare the previous snapshot (if any) against the current unified
    parcel table, emit ChangeEvent rows, then save the new snapshot for
    next time.
    """
    previous = {p["parcel_id"]: p for p in load_snapshot()}
    current_parcels = db.query(UnifiedParcel).all()
    current = {p.parcel_id: p for p in current_parcels}

    db.query(ChangeEvent).delete()
    count = 0

    # New parcels/buildings
    for parcel_id, p in current.items():
        if parcel_id not in previous:
            db.add(ChangeEvent(
                id=new_id("CE"), job_id=job_id, feature_ref=p.id, change_type="new",
                before=None,
                after={"parcel_id": p.parcel_id, "owner_name": p.owner_name, "area": p.area,
                       "building_count": p.building_count},
                confidence=p.confidence_score, detected_at=datetime.utcnow(),
            ))
            count += 1

    # Removed parcels
    for parcel_id, prev in previous.items():
        if parcel_id not in current:
            db.add(ChangeEvent(
                id=new_id("CE"), job_id=job_id, feature_ref=prev["id"], change_type="removed",
                before=prev, after=None, confidence=80.0, detected_at=datetime.utcnow(),
            ))
            count += 1

    # Modified parcels (attribute or building count changes)
    for parcel_id, p in current.items():
        prev = previous.get(parcel_id)
        if not prev:
            continue
        changed_fields = {}
        for field in ("owner_name", "land_use", "building_count"):
            if str(prev.get(field)) != str(getattr(p, field)):
                changed_fields[field] = {"before": prev.get(field), "after": getattr(p, field)}
        if changed_fields:
            change_type = "attribute_changed"
            if "building_count" in changed_fields:
                change_type = "modified"
            db.add(ChangeEvent(
                id=new_id("CE"), job_id=job_id, feature_ref=p.id, change_type=change_type,
                before={k: v["before"] for k, v in changed_fields.items()},
                after={k: v["after"] for k, v in changed_fields.items()},
                confidence=p.confidence_score, detected_at=datetime.utcnow(),
            ))
            count += 1

        # Area change beyond noise threshold
        if prev.get("area") and p.area:
            rel_diff = abs(prev["area"] - p.area) / max(prev["area"], p.area)
            if rel_diff > 0.05:
                db.add(ChangeEvent(
                    id=new_id("CE"), job_id=job_id, feature_ref=p.id, change_type="geometry_changed",
                    before={"area": prev["area"]}, after={"area": p.area},
                    confidence=round((1 - rel_diff) * 100, 1), detected_at=datetime.utcnow(),
                ))
                count += 1

    count += _detect_source_version_changes(db, job_id)
    db.commit()
    save_snapshot(db)
    logger.info(f"Change detection found {count} events")
    return count
