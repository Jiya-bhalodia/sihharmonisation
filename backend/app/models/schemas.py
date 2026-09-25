"""
Pydantic schemas (API request/response contracts) for BHUMI-X.
"""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class DatasetOut(BaseModel):
    id: str
    name: str
    department: str
    source_type: str
    geometry_type: Optional[str]
    crs: Optional[str]
    feature_count: int
    quality_score: float
    status: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class ParcelOut(BaseModel):
    id: str
    parcel_id: str
    survey_number: Optional[str]
    owner_name: Optional[str]
    area: Optional[float]
    land_use: Optional[str]
    geometry_geojson: Optional[str]
    building_count: int
    utility_count: int
    gnss_verified: bool
    ground_truth_verified: bool
    source_count: int
    confidence_score: float
    spatial_confidence: float
    attribute_confidence: float
    geometry_confidence: float
    source_agreement: float
    validation_status: str
    conflict_status: str
    lineage: dict
    last_updated: datetime

    class Config:
        from_attributes = True


class MatchOut(BaseModel):
    id: str
    matched_group_id: str
    feature_id: str
    dataset_id: str
    parcel_unified_id: Optional[str]
    spatial_proximity: float
    geometry_overlap: float
    area_similarity: float
    attribute_similarity: float
    overall_confidence: float

    class Config:
        from_attributes = True


class ConflictOut(BaseModel):
    id: str
    conflict_type: str
    severity: str
    feature_ref: Optional[str]
    source_a: Optional[str]
    source_b: Optional[str]
    description: Optional[str]
    confidence: float
    recommended_action: Optional[str]
    status: str
    parcel_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ConflictResolveRequest(BaseModel):
    status: str  # Under Review, Resolved, Accepted, Rejected
    note: Optional[str] = None


class ChangeEventOut(BaseModel):
    id: str
    feature_ref: str
    change_type: str
    before: Optional[Any]
    after: Optional[Any]
    confidence: float
    detected_at: datetime

    class Config:
        from_attributes = True


class HarmonizationJobOut(BaseModel):
    id: str
    status: str
    stages: list
    total_processed: int
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class AttributeMappingOut(BaseModel):
    id: str
    dataset_id: str
    source_field: str
    canonical_field: str
    confidence: float
    method: str
    manual_override: bool

    class Config:
        from_attributes = True


class MappingOverrideRequest(BaseModel):
    canonical_field: str


class StatisticsOut(BaseModel):
    total_parcels: int
    total_buildings: int
    total_datasets: int
    matched_features: int
    total_conflicts: int
    open_conflicts: int
    average_confidence: float
    topology_errors: int
    changes_detected: int
    dataset_feature_distribution: list
    confidence_distribution: dict
    conflict_categories: dict
    data_quality_scores: list