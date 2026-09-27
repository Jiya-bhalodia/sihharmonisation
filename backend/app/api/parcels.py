"""
Unified land record (parcel) endpoints: list, detail with lineage, search/filter.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.orm import UnifiedParcel, User
from app.models.schemas import ParcelOut
from app.security import current_user

router = APIRouter()


@router.get("", response_model=List[ParcelOut])
def get_parcels(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search by parcel_id or owner_name"),
    land_use: Optional[str] = Query(None),
    validation_status: Optional[str] = Query(None),
    conflict_status: Optional[str] = Query(None),
    min_confidence: Optional[float] = Query(None),
    sort_by: str = Query("confidence_score"),
    sort_dir: str = Query("desc"),
    limit: int = Query(500, le=2000),
    user: User | None = Depends(current_user),
):
    can_view_owners = user is None or user.role in {"revenue_officer", "reviewer", "administrator"}
    query = db.query(UnifiedParcel)
    if search:
        like = f"%{search}%"
        search_filter = UnifiedParcel.parcel_id.ilike(like)
        if can_view_owners:
            search_filter = search_filter | UnifiedParcel.owner_name.ilike(like)
        query = query.filter(search_filter)
    if land_use:
        query = query.filter(UnifiedParcel.land_use == land_use)
    if validation_status:
        query = query.filter(UnifiedParcel.validation_status == validation_status)
    if conflict_status:
        query = query.filter(UnifiedParcel.conflict_status == conflict_status)
    if min_confidence is not None:
        query = query.filter(UnifiedParcel.confidence_score >= min_confidence)

    sort_column = getattr(UnifiedParcel, sort_by, UnifiedParcel.confidence_score)
    query = query.order_by(sort_column.desc() if sort_dir == "desc" else sort_column.asc())

    parcels = query.limit(limit).all()
    if not can_view_owners:
        return [ParcelOut.model_validate(parcel).model_copy(update={"owner_name": "REDACTED"}) for parcel in parcels]
    return parcels


@router.get("/{parcel_id}", response_model=ParcelOut)
def get_parcel_detail(parcel_id: str, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    parcel = db.query(UnifiedParcel).filter(UnifiedParcel.id == parcel_id).first()
    if not parcel:
        raise HTTPException(status_code=404, detail="Parcel not found")
    if user is not None and user.role not in {"revenue_officer", "reviewer", "administrator"}:
        return ParcelOut.model_validate(parcel).model_copy(update={"owner_name": "REDACTED"})
    return parcel
