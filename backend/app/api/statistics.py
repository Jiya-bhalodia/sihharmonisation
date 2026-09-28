"""
Dashboard aggregate statistics + data quality report endpoints.
All numbers here are computed live from the database -- nothing is
hardcoded.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from collections import Counter

from app.database import get_db
from app.models.orm import (
    Dataset, Feature, UnifiedParcel, Conflict, MatchRecord,
    ValidationResult, ChangeEvent
)
from app.models.schemas import StatisticsOut
from app.ml.spatial_matcher import confidence_band

router = APIRouter()


@router.get("", response_model=StatisticsOut)
def get_statistics(db: Session = Depends(get_db)):
    datasets = db.query(Dataset).all()
    parcels = db.query(UnifiedParcel).all()
    conflicts = db.query(Conflict).all()
    matches = db.query(MatchRecord).all()
    validation_issues = db.query(ValidationResult).filter(ValidationResult.is_valid == False).all()  # noqa: E712
    changes = db.query(ChangeEvent).all()

    total_buildings = sum(p.building_count for p in parcels)
    avg_confidence = round(sum(p.confidence_score for p in parcels) / len(parcels), 1) if parcels else 0.0
    open_conflicts = sum(1 for c in conflicts if c.status == "Open")

    dataset_feature_distribution = [
        {"name": d.name, "source_type": d.source_type, "count": d.feature_count} for d in datasets
    ]

    band_counts = Counter(confidence_band(m.overall_confidence) for m in matches)
    confidence_distribution = {
        "High": band_counts.get("High", 0),
        "Medium": band_counts.get("Medium", 0),
        "Low": band_counts.get("Low", 0),
    }

    conflict_type_counts = Counter(c.conflict_type for c in conflicts)
    conflict_categories = dict(conflict_type_counts)

    data_quality_scores = [
        {"name": d.name, "quality_score": d.quality_score} for d in datasets
    ]

    return StatisticsOut(
        total_parcels=len(parcels),
        total_buildings=total_buildings,
        total_datasets=len(datasets),
        matched_features=len(matches),
        total_conflicts=len(conflicts),
        open_conflicts=open_conflicts,
        average_confidence=avg_confidence,
        topology_errors=len(validation_issues),
        changes_detected=len(changes),
        dataset_feature_distribution=dataset_feature_distribution,
        confidence_distribution=confidence_distribution,
        conflict_categories=conflict_categories,
        data_quality_scores=data_quality_scores,
    )


quality_router = APIRouter()


@quality_router.get("")
def get_data_quality(db: Session = Depends(get_db)):
    datasets = db.query(Dataset).all()
    report = []
    for d in datasets:
        invalid_count = db.query(ValidationResult).filter(
            ValidationResult.dataset_id == d.id, ValidationResult.is_valid == False  # noqa: E712
        ).count()
        report.append({
            "dataset_id": d.id,
            "name": d.name,
            "department": d.department,
            "source_type": d.source_type,
            "feature_count": d.feature_count,
            "quality_score": d.quality_score,
            "invalid_geometry_count": invalid_count,
            "crs": d.crs,
            "status": d.status,
        })
    return report


@quality_router.get("/topology")
def get_topology_results(db: Session = Depends(get_db)):
    """Return persisted validation evidence, including original/corrected geometry snapshots."""
    rows = db.query(ValidationResult).order_by(ValidationResult.dataset_id, ValidationResult.id).all()
    return [{
        "id": row.id,
        "dataset_id": row.dataset_id,
        "feature_id": row.feature_id,
        "issue_type": row.issue_type,
        "is_valid": row.is_valid,
        "corrected": row.corrected,
        "original_geometry": row.original_geometry,
        "corrected_geometry": row.corrected_geometry,
    } for row in rows]
