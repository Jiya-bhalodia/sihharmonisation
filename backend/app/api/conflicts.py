"""
Spatial conflict endpoints: list and resolve.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from app.database import get_db
from app.models.orm import Conflict
from app.models.schemas import ConflictOut, ConflictResolveRequest
from app.models.orm import User
from app.security import current_user, require_permission, write_audit

router = APIRouter()

VALID_STATUSES = {"Open", "Under Review", "Resolved", "Accepted", "Rejected"}


@router.get("", response_model=List[ConflictOut])
def get_conflicts(
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    conflict_type: Optional[str] = Query(None),
):
    query = db.query(Conflict)
    if user is not None and user.role not in {"revenue_officer", "reviewer", "administrator"}:
        query = query.filter(Conflict.conflict_type != "owner_mismatch")
    if status:
        query = query.filter(Conflict.status == status)
    if severity:
        query = query.filter(Conflict.severity == severity)
    if conflict_type:
        query = query.filter(Conflict.conflict_type == conflict_type)
    return query.order_by(Conflict.created_at.desc()).all()


@router.post("/{conflict_id}/resolve", response_model=ConflictOut)
def resolve_conflict(conflict_id: str, req: ConflictResolveRequest, request: Request,
                     db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    require_permission(user, "review")
    if req.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    conflict = db.query(Conflict).filter(Conflict.id == conflict_id).first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    previous = {"status": conflict.status, "resolved_at": conflict.resolved_at.isoformat() if conflict.resolved_at else None}
    conflict.status = req.status
    if req.status in ("Resolved", "Accepted", "Rejected"):
        conflict.resolved_at = datetime.utcnow()
    write_audit(db, user, "conflict.status_changed", "conflict", conflict.id, request,
                before=previous, after={"status": conflict.status, "resolved_at": conflict.resolved_at.isoformat() if conflict.resolved_at else None})
    db.commit()
    db.refresh(conflict)
    return conflict
