"""Endpoints for a single-AOI pilot's technical readiness."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.pilot_service import get_pilot_readiness

router = APIRouter()


@router.get("/readiness")
def pilot_readiness(db: Session = Depends(get_db)):
    return get_pilot_readiness(db)
