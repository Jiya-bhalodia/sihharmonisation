"""
AI spatial match endpoints, including attribute mapping table access.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.orm import MatchRecord, AttributeMapping
from app.models.schemas import MatchOut, AttributeMappingOut, MappingOverrideRequest
from app.models.orm import User
from app.security import current_user, require_permission, write_audit

router = APIRouter()


@router.get("", response_model=List[MatchOut])
def get_matches(
    db: Session = Depends(get_db),
    group_id: Optional[str] = Query(None),
    min_confidence: Optional[float] = Query(None),
    limit: int = Query(500, le=3000),
):
    query = db.query(MatchRecord)
    if group_id:
        query = query.filter(MatchRecord.matched_group_id == group_id)
    if min_confidence is not None:
        query = query.filter(MatchRecord.overall_confidence >= min_confidence)
    return query.order_by(MatchRecord.overall_confidence.desc()).limit(limit).all()


mappings_router = APIRouter()


@mappings_router.get("", response_model=List[AttributeMappingOut])
def get_mappings(db: Session = Depends(get_db), dataset_id: Optional[str] = Query(None)):
    query = db.query(AttributeMapping)
    if dataset_id:
        query = query.filter(AttributeMapping.dataset_id == dataset_id)
    return query.all()


@mappings_router.post("/{mapping_id}/override", response_model=AttributeMappingOut)
def override_mapping(mapping_id: str, req: MappingOverrideRequest, request: Request,
                     db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    require_permission(user, "review")
    mapping = db.query(AttributeMapping).filter(AttributeMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    previous = mapping.canonical_field
    mapping.canonical_field = req.canonical_field
    mapping.manual_override = True
    mapping.confidence = 100.0
    write_audit(db, user, "attribute_mapping.overridden", "attribute_mapping", mapping.id, request,
                before={"canonical_field": previous}, after={"canonical_field": mapping.canonical_field})
    db.commit()
    db.refresh(mapping)
    return mapping
