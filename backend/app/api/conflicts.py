"""
Spatial conflict endpoints: list and resolve.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from app.database import get_db
from app.models.orm import Conflict
from app.models.schemas import ConflictOut, ConflictResolveRequest

router = APIRouter()

VALID_STATUSES = {"Open", "Under Review", "Resolved", "Accepted", "Rejected"}


@router.get("", response_model=List[ConflictOut])
def get_conflicts(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    conflict_type: Optional[str] = Query(None),
):
    query = db.query(Conflict)
    if status:
        query = query.filter(Conflict.status == status)
    if severity:
        query = query.filter(Conflict.severity == severity)
    if conflict_type:
        query = query.filter(Conflict.conflict_type == conflict_type)
    return query.order_by(Conflict.created_at.desc()).all()


@router.post("/{conflict_id}/resolve", response_model=ConflictOut)
def resolve_conflict(conflict_id: str, req: ConflictResolveRequest, db: Session = Depends(get_db)):
    if req.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    conflict = db.query(Conflict).filter(Conflict.id == conflict_id).first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    conflict.status = req.status
    if req.status in ("Resolved", "Accepted", "Rejected"):
        conflict.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(conflict)
    return conflict