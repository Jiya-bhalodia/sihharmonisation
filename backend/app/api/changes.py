"""
Change detection endpoints.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.orm import ChangeEvent
from app.models.schemas import ChangeEventOut

router = APIRouter()


@router.get("", response_model=List[ChangeEventOut])
def get_changes(db: Session = Depends(get_db), change_type: Optional[str] = Query(None)):
    query = db.query(ChangeEvent)
    if change_type:
        query = query.filter(ChangeEvent.change_type == change_type)
    return query.order_by(ChangeEvent.detected_at.desc()).all()