"""
Export service: produces GeoJSON / CSV representations of the unified
land record for download.
"""
import json
import csv
import io
from typing import List
from sqlalchemy.orm import Session
from app.models.orm import UnifiedParcel


def export_geojson(db: Session) -> dict:
    parcels = db.query(UnifiedParcel).all()
    features = []
    for p in parcels:
        geometry = json.loads(p.geometry_geojson) if p.geometry_geojson else None
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "id": p.id,
                "parcel_id": p.parcel_id,
                "survey_number": p.survey_number,
                "owner_name": p.owner_name,
                "area": p.area,
                "land_use": p.land_use,
                "building_count": p.building_count,
                "utility_count": p.utility_count,
                "gnss_verified": p.gnss_verified,
                "ground_truth_verified": p.ground_truth_verified,
                "source_count": p.source_count,
                "confidence_score": p.confidence_score,
                "validation_status": p.validation_status,
                "conflict_status": p.conflict_status,
                "last_updated": p.last_updated.isoformat() if p.last_updated else None,
            },
        })
    return {"type": "FeatureCollection", "features": features}


def export_csv(db: Session) -> str:
    parcels = db.query(UnifiedParcel).all()
    output = io.StringIO()
    fieldnames = [
        "id", "parcel_id", "survey_number", "owner_name", "area", "land_use",
        "building_count", "utility_count", "gnss_verified", "ground_truth_verified",
        "source_count", "confidence_score", "validation_status", "conflict_status", "last_updated",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for p in parcels:
        writer.writerow({
            "id": p.id, "parcel_id": p.parcel_id, "survey_number": p.survey_number,
            "owner_name": p.owner_name, "area": p.area, "land_use": p.land_use,
            "building_count": p.building_count, "utility_count": p.utility_count,
            "gnss_verified": p.gnss_verified, "ground_truth_verified": p.ground_truth_verified,
            "source_count": p.source_count, "confidence_score": p.confidence_score,
            "validation_status": p.validation_status, "conflict_status": p.conflict_status,
            "last_updated": p.last_updated.isoformat() if p.last_updated else None,
        })
    return output.getvalue()