"""
SQLAlchemy ORM models for BHUMI-X.

Geometry is stored as GeoJSON text for portability in demo/SQLite mode.
When migrated to PostgreSQL+PostGIS, these Text columns can be swapped
for geoalchemy2.Geometry columns without changing service-layer logic,
since services already parse/emit GeoJSON via Shapely.
"""
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, Text, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    department = Column(String, nullable=False)
    source_type = Column(String, nullable=False)   # cadastral, revenue, municipal, gnss, ground_truth, utility, drone
    provenance = Column(String, nullable=False, default="user_upload")
    geometry_type = Column(String, nullable=True)   # Polygon, Point, LineString, Table
    crs = Column(String, nullable=True)
    feature_count = Column(Integer, default=0)
    quality_score = Column(Float, default=0.0)
    status = Column(String, default="uploaded")     # uploaded, processing, harmonized, error
    file_path = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    features = relationship("Feature", back_populates="dataset", cascade="all, delete-orphan")


class Feature(Base):
    __tablename__ = "features"

    id = Column(String, primary_key=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    canonical_type = Column(String, nullable=False)  # parcel, building, gnss_point, ground_truth, utility
    raw_properties = Column(JSON, default=dict)
    geometry_geojson = Column(Text, nullable=True)
    centroid_lat = Column(Float, nullable=True)
    centroid_lon = Column(Float, nullable=True)
    area_sqm = Column(Float, nullable=True)
    is_valid_geometry = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="features")


class UnifiedParcel(Base):
    __tablename__ = "unified_parcels"

    id = Column(String, primary_key=True)
    parcel_id = Column(String, nullable=False, index=True)
    survey_number = Column(String, nullable=True)
    owner_name = Column(String, nullable=True)
    area = Column(Float, nullable=True)
    land_use = Column(String, nullable=True)
    geometry_geojson = Column(Text, nullable=True)
    building_count = Column(Integer, default=0)
    utility_count = Column(Integer, default=0)
    gnss_verified = Column(Boolean, default=False)
    ground_truth_verified = Column(Boolean, default=False)
    source_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.0)
    spatial_confidence = Column(Float, default=0.0)
    attribute_confidence = Column(Float, default=0.0)
    geometry_confidence = Column(Float, default=0.0)
    source_agreement = Column(Float, default=0.0)
    validation_status = Column(String, default="PENDING")  # PASSED, FAILED, PENDING
    conflict_status = Column(String, default="NONE")        # NONE, MINOR, MAJOR
    lineage = Column(JSON, default=dict)   # {source_type: {dataset_id, feature_id, contributed_fields:[]}}
    last_updated = Column(DateTime, default=datetime.utcnow)


class MatchRecord(Base):
    __tablename__ = "matches"

    id = Column(String, primary_key=True)
    parcel_unified_id = Column(String, ForeignKey("unified_parcels.id"), nullable=True)
    feature_id = Column(String, ForeignKey("features.id"), nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    matched_group_id = Column(String, nullable=False, index=True)  # groups features believed to be the same real-world parcel
    spatial_proximity = Column(Float, default=0.0)
    geometry_overlap = Column(Float, default=0.0)
    area_similarity = Column(Float, default=0.0)
    attribute_similarity = Column(Float, default=0.0)
    overall_confidence = Column(Float, default=0.0)
    matched_at = Column(DateTime, default=datetime.utcnow)


class Conflict(Base):
    __tablename__ = "conflicts"

    id = Column(String, primary_key=True)
    conflict_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)   # MINOR, MODERATE, MAJOR
    feature_ref = Column(String, nullable=True)
    source_a = Column(String, nullable=True)
    source_b = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    recommended_action = Column(String, nullable=True)
    status = Column(String, default="Open")  # Open, Under Review, Resolved, Accepted, Rejected
    parcel_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class AttributeMapping(Base):
    __tablename__ = "attribute_mappings"

    id = Column(String, primary_key=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    source_field = Column(String, nullable=False)
    canonical_field = Column(String, nullable=False)
    confidence = Column(Float, default=0.0)
    method = Column(String, default="fuzzy_synonym")
    manual_override = Column(Boolean, default=False)


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id = Column(String, primary_key=True)
    feature_id = Column(String, ForeignKey("features.id"), nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    is_valid = Column(Boolean, default=True)
    issue_type = Column(String, nullable=True)  # self_intersection, duplicate, overlap, sliver, invalid, none
    original_geometry = Column(Text, nullable=True)
    corrected_geometry = Column(Text, nullable=True)
    corrected = Column(Boolean, default=False)


class HarmonizationJob(Base):
    __tablename__ = "harmonization_jobs"

    id = Column(String, primary_key=True)
    status = Column(String, default="queued")  # queued, running, completed, failed
    stages = Column(JSON, default=list)
    total_processed = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class ChangeEvent(Base):
    __tablename__ = "change_events"

    id = Column(String, primary_key=True)
    job_id = Column(String, nullable=True)
    feature_ref = Column(String, nullable=False)
    change_type = Column(String, nullable=False)  # new, removed, modified, geometry_changed, attribute_changed
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    confidence = Column(Float, default=0.0)
    detected_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True, index=True)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    actor_email = Column(String, nullable=False)
    action = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=True, index=True)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
