"""
Unified land record (parcel) endpoints: list, detail with lineage, search/filter.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.orm import UnifiedParcel
from app.models.schemas import ParcelOut

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
):
    query = db.query(UnifiedParcel)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (UnifiedParcel.parcel_id.ilike(like)) | (UnifiedParcel.owner_name.ilike(like))
        )
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

    return query.limit(limit).all()


@router.get("/{parcel_id}", response_model=ParcelOut)
def get_parcel_detail(parcel_id: str, db: Session = Depends(get_db)):
    parcel = db.query(UnifiedParcel).filter(UnifiedParcel.id == parcel_id).first()
    if not parcel:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return parcel