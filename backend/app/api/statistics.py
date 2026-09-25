"""
Dataset ingestion endpoints: list datasets and upload new ones
(GeoJSON, CSV with lat/lon, or Shapefile ZIP).
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.schemas import DatasetOut
from app.models.orm import Dataset, AttributeMapping
from app.services import dataset_service
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger("api.datasets")


@router.get("", response_model=List[DatasetOut])
def get_datasets(db: Session = Depends(get_db)):
    return dataset_service.list_datasets(db)


@router.post("/upload", response_model=DatasetOut)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(...),
    department: str = Form(...),
    source_type: str = Form(...),
    lat_field: str = Form("latitude"),
    lon_field: str = Form("longitude"),
    db: Session = Depends(get_db),
):
    valid_source_types = {"cadastral", "revenue", "municipal", "gnss", "ground_truth", "utility", "drone"}
    if source_type not in valid_source_types:
        raise HTTPException(status_code=400, detail=f"source_type must be one of {sorted(valid_source_types)}")

    filename = (file.filename or "").lower()
    contents = await file.read()

    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        if filename.endswith(".geojson") or filename.endswith(".json"):
            dataset = dataset_service.ingest_geojson_file(db, contents, name, department, source_type)
        elif filename.endswith(".csv"):
            dataset = dataset_service.ingest_csv_latlon(db, contents, name, department, source_type,
                                                          lat_field=lat_field, lon_field=lon_field)
        elif filename.endswith(".zip"):
            dataset = dataset_service.ingest_shapefile_zip(db, contents, name, department, source_type)
        else:
            raise HTTPException(status_code=400,
                                 detail="Unsupported file type. Use .geojson, .csv, or a zipped shapefile (.zip)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed for {filename}: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to parse uploaded file: {str(e)}")

    return dataset


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    db.query(AttributeMapping).filter(AttributeMapping.dataset_id == dataset_id).delete()
    db.delete(dataset)
    db.commit()
    return {"status": "deleted", "id": dataset_id}

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