"""
Spatial conflict detection service.

Detects: parcel-parcel overlaps, building-crossing-parcel-boundary,
utility-crossing-parcel, area mismatches, duplicate IDs,
GNSS-point-outside-parcel, and conflicting owner attributes between
matched sources.

Fixed after senior review: area-mismatch and owner-mismatch detection now
always include each group's anchor feature (typically the authoritative
cadastral parcel). Previously these two checks only looked at
MatchRecord rows, which no longer include the anchor since a fabricated
100%-confidence self-match record for the anchor was removed -- without
this fix, the cadastral parcel's own area/owner would have silently
dropped out of every comparison.
"""
from typing import List, Dict
from sqlalchemy.orm import Session
from datetime import datetime
from collections import defaultdict

from app.models.orm import Conflict, MatchRecord, Feature, Dataset
from app.utils.ids import new_id
from app.utils.logger import get_logger
from app.geo.geometry_utils import iou, point_in_polygon_proximity
from app.ml.spatial_matcher import MatchCandidate

logger = get_logger("services.conflict")

AREA_MISMATCH_THRESHOLD = 0.15   # 15% relative area difference triggers a conflict
BOUNDARY_CROSS_MIN_IOU = 0.02
BOUNDARY_CROSS_MAX_IOU = 0.85    # if IoU is this high the building is essentially inside, not crossing


def detect_all_conflicts(db: Session, candidates: List[MatchCandidate], matched_groups: Dict[str, MatchCandidate]) -> int:
    db.query(Conflict).filter(Conflict.status == "Open").delete()
    db.commit()

    count = 0
    count += _detect_parcel_overlaps(db, candidates)
    count += _detect_building_boundary_crossings(db, candidates)
    count += _detect_utility_crossings(db, candidates)
    count += _detect_area_mismatches(db, matched_groups)
    count += _detect_duplicate_ids(db)
    count += _detect_gnss_outside_parcel(db, candidates)
    count += _detect_owner_conflicts(db, matched_groups)
    db.commit()
    return count


def _add_conflict(db, conflict_type, severity, feature_ref, source_a, source_b, description, confidence, action):
    db.add(Conflict(
        id=new_id("CF"),
        conflict_type=conflict_type,
        severity=severity,
        feature_ref=feature_ref,
        source_a=source_a,
        source_b=source_b,
        description=description,
        confidence=confidence,
        recommended_action=action,
        status="Open",
        created_at=datetime.utcnow(),
    ))


def _detect_parcel_overlaps(db: Session, candidates: List[MatchCandidate]) -> int:
    parcels = [c for c in candidates if c.canonical_type == "parcel" and c.geometry is not None]
    count = 0
    for i in range(len(parcels)):
        for j in range(i + 1, len(parcels)):
            a, b = parcels[i], parcels[j]
            if a.dataset_id != b.dataset_id:
                continue  # only flag overlaps within the same authoritative layer
            overlap = iou(a.geometry, b.geometry)
            if 0.05 < overlap < 0.97:
                _add_conflict(
                    db, "parcel_overlap", "MODERATE" if overlap < 0.3 else "MAJOR",
                    a.feature_id, a.dataset_id, b.dataset_id,
                    f"Parcels {a.feature_id} and {b.feature_id} overlap by {overlap*100:.1f}% (IoU)",
                    round(overlap * 100, 1), "Review parcel boundaries and adjust geometry"
                )
                count += 1
    return count


def _detect_building_boundary_crossings(db: Session, candidates: List[MatchCandidate]) -> int:
    parcels = [c for c in candidates if c.canonical_type == "parcel" and c.geometry is not None]
    buildings = [c for c in candidates if c.canonical_type == "building" and c.geometry is not None]
    count = 0
    for building in buildings:
        for parcel in parcels:
            if building.geometry.is_empty or parcel.geometry.is_empty:
                continue
            overlap = iou(building.geometry, parcel.geometry)
            if BOUNDARY_CROSS_MIN_IOU < overlap < BOUNDARY_CROSS_MAX_IOU:
                _add_conflict(
                    db, "building_boundary_crossing", "MINOR" if overlap > 0.5 else "MODERATE",
                    building.feature_id, building.dataset_id, parcel.dataset_id,
                    f"Building {building.feature_id} crosses parcel {parcel.feature_id} boundary "
                    f"(overlap ratio {overlap*100:.1f}%)",
                    round((1 - overlap) * 100, 1), "Verify building footprint against surveyed parcel boundary"
                )
                count += 1
                break
    return count


def _detect_utility_crossings(db: Session, candidates: List[MatchCandidate]) -> int:
    parcels = [c for c in candidates if c.canonical_type == "parcel" and c.geometry is not None]
    utilities = [c for c in candidates if c.canonical_type == "utility" and c.geometry is not None]
    count = 0
    for utility in utilities:
        for parcel in parcels:
            try:
                if utility.geometry.is_empty or parcel.geometry.is_empty:
                    continue
                if utility.geometry.intersects(parcel.geometry) and not parcel.geometry.contains(utility.geometry):
                    _add_conflict(
                        db, "utility_crossing", "MINOR",
                        utility.feature_id, utility.dataset_id, parcel.dataset_id,
                        f"Utility line {utility.feature_id} crosses parcel {parcel.feature_id} boundary",
                        70.0, "Coordinate with Utility Department for easement verification"
                    )
                    count += 1
                    break
            except Exception:
                continue
    return count


def _detect_area_mismatches(db: Session, matched_groups: Dict[str, MatchCandidate]) -> int:
    """Compare area of matched features across sources within the same
    group, always including the group's anchor feature (typically the
    authoritative cadastral parcel)."""
    groups = defaultdict(list)
    for rec in db.query(MatchRecord).all():
        groups[rec.matched_group_id].append(rec)

    count = 0
    for group_id, anchor in matched_groups.items():
        records = groups.get(group_id, [])
        feature_ids = [r.feature_id for r in records]
        features = db.query(Feature).filter(Feature.id.in_(feature_ids)).all() if feature_ids else []
        areas = [(f, f.area_sqm) for f in features if f.area_sqm and f.area_sqm > 0]

        anchor_feature = db.query(Feature).filter(Feature.id == anchor.feature_id).first()
        if anchor_feature and anchor_feature.area_sqm and anchor_feature.area_sqm > 0:
            areas.append((anchor_feature, anchor_feature.area_sqm))

        if len(areas) < 2:
            continue
        max_area = max(a for _, a in areas)
        min_area = min(a for _, a in areas)
        if max_area <= 0:
            continue
        rel_diff = (max_area - min_area) / max_area
        if rel_diff > AREA_MISMATCH_THRESHOLD:
            f_max = next(f for f, a in areas if a == max_area)
            f_min = next(f for f, a in areas if a == min_area)
            _add_conflict(
                db, "area_mismatch", "MODERATE" if rel_diff < 0.3 else "MAJOR",
                f_max.id, f_max.dataset_id, f_min.dataset_id,
                f"Area mismatch of {rel_diff*100:.1f}% between sources for group {group_id} "
                f"({min_area:.1f} m² vs {max_area:.1f} m²)",
                round((1 - rel_diff) * 100, 1), "Reconcile recorded area against ground survey"
            )
            count += 1
    return count


def _detect_duplicate_ids(db: Session) -> int:
    count = 0
    for dataset in db.query(Dataset).all():
        features = db.query(Feature).filter(Feature.dataset_id == dataset.id).all()
        seen = {}
        for f in features:
            props = f.raw_properties or {}
            key = None
            for candidate_key in ("parcel_id", "survey_no", "property_id", "khasra_no", "plot_no"):
                if candidate_key in props and props[candidate_key]:
                    key = str(props[candidate_key])
                    break
            if key is None:
                continue
            if key in seen:
                _add_conflict(
                    db, "duplicate_id", "MODERATE",
                    f.id, dataset.id, dataset.id,
                    f"Duplicate identifier '{key}' found in dataset {dataset.name} "
                    f"(features {seen[key]} and {f.id})",
                    85.0, "De-duplicate records and verify with source department"
                )
                count += 1
            else:
                seen[key] = f.id
    return count


def _detect_gnss_outside_parcel(db: Session, candidates: List[MatchCandidate]) -> int:
    parcels = [c for c in candidates if c.canonical_type == "parcel" and c.geometry is not None]
    gnss_points = [c for c in candidates if c.canonical_type == "gnss_point" and c.geometry is not None]
    count = 0
    for point in gnss_points:
        best_proximity = 0.0
        for parcel in parcels:
            score = point_in_polygon_proximity(point.geometry, parcel.geometry)
            best_proximity = max(best_proximity, score)
        if best_proximity < 0.3:
            _add_conflict(
                db, "gnss_outside_parcel", "MINOR",
                point.feature_id, point.dataset_id, None,
                f"GNSS survey point {point.feature_id} lies outside all known parcel boundaries "
                f"(nearest match confidence {best_proximity*100:.1f}%)",
                round(best_proximity * 100, 1), "Re-verify GNSS point placement in field"
            )
            count += 1
    return count


def _detect_owner_conflicts(db: Session, matched_groups: Dict[str, MatchCandidate]) -> int:
    from difflib import SequenceMatcher
    groups = defaultdict(list)
    for rec in db.query(MatchRecord).all():
        groups[rec.matched_group_id].append(rec)

    count = 0
    for group_id, anchor in matched_groups.items():
        records = groups.get(group_id, [])
        feature_ids = [r.feature_id for r in records]
        features = db.query(Feature).filter(Feature.id.in_(feature_ids)).all() if feature_ids else []

        owner_entries = []
        anchor_feature = db.query(Feature).filter(Feature.id == anchor.feature_id).first()
        if anchor_feature:
            props = anchor_feature.raw_properties or {}
            for key in ("owner", "owner_name", "landholder", "property_owner"):
                if key in props and props[key]:
                    owner_entries.append((anchor_feature, str(props[key])))
                    break
        for f in features:
            props = f.raw_properties or {}
            for key in ("owner", "owner_name", "landholder", "property_owner"):
                if key in props and props[key]:
                    owner_entries.append((f, str(props[key])))
                    break

        if len(owner_entries) < 2:
            continue
        base_feature, base_name = owner_entries[0]
        for f, name in owner_entries[1:]:
            similarity = SequenceMatcher(None, base_name.strip().lower(), name.strip().lower()).ratio()
            if similarity < 0.6:
                _add_conflict(
                    db, "owner_mismatch", "MODERATE",
                    f.id, base_feature.dataset_id, f.dataset_id,
                    f"Conflicting owner names for group {group_id}: '{base_name}' vs '{name}' "
                    f"(name similarity {similarity*100:.1f}%)",
                    round(similarity * 100, 1), "Cross-verify ownership with Revenue Department records"
                )
                count += 1
    return count