"""
Change detection endpoints.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.orm import ChangeEvent
from app.models.schemas import ChangeEventOut
from app.models.orm import User
from app.security import current_user
from app.config import get_settings
from app.services.change_service import hosted_demo_change_events

router = APIRouter()


def _mask_personal_fields(value):
    if isinstance(value, dict):
        return {key: ("REDACTED" if key.lower() in {"owner", "owner_name", "landholder", "property_owner"}
                      else _mask_personal_fields(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_personal_fields(item) for item in value]
    return value


@router.get("", response_model=List[ChangeEventOut])
def get_changes(db: Session = Depends(get_db), change_type: Optional[str] = Query(None),
                user: User | None = Depends(current_user)):
    # ChangeEvent rows can be inspected, but this hosted profile deliberately
    # uses a deterministic vector fixture comparison instead of a local disk snapshot.
    if get_settings().FREE_DEMO_MODE:
        events = hosted_demo_change_events(db)
        if change_type:
            events = [event for event in events if event["change_type"] == change_type]
        if user is None or user.role in {"revenue_officer", "reviewer", "administrator"}:
            return [ChangeEventOut.model_validate(event) for event in events]
        return [ChangeEventOut.model_validate({
            **event,
            "before": _mask_personal_fields(event.get("before")),
            "after": _mask_personal_fields(event.get("after")),
        }) for event in events]
    query = db.query(ChangeEvent)
    if change_type:
        query = query.filter(ChangeEvent.change_type == change_type)
    rows = query.order_by(ChangeEvent.detected_at.desc()).all()
    if user is None or user.role in {"revenue_officer", "reviewer", "administrator"}:
        return rows
    return [ChangeEventOut.model_validate(row).model_copy(update={
        "before": _mask_personal_fields(row.before), "after": _mask_personal_fields(row.after)
    }) for row in rows]
