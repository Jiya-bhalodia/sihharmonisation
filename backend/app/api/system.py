"""
System status endpoints: health check and API metadata.
"""
from fastapi import APIRouter
from datetime import datetime
from app.config import get_settings

router = APIRouter()
settings = get_settings()

START_TIME = datetime.utcnow()


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "demo_mode": settings.DEMO_MODE,
        "uptime_seconds": (datetime.utcnow() - START_TIME).total_seconds(),
        "database": "SQLite (Demo Mode)" if settings.DEMO_MODE else "PostgreSQL + PostGIS",
        "target_crs": settings.TARGET_CRS,
    }