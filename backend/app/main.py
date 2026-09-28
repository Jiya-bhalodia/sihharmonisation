"""
BHUMI-X FastAPI application entrypoint.

AI-Powered Urban Land Record Harmonization Platform
Ministry of Rural Development -- Problem Statement 26013

Run (from backend/ directory):
    uvicorn app.main:app --reload --port 8000

Swagger UI available at http://localhost:8000/docs
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.utils.logger import get_logger

from app.api import (
    system, datasets, parcels, harmonize, matches, conflicts, changes,
    statistics, export, pilot,
)
from app.api import auth
from app.security import current_user

settings = get_settings()
logger = get_logger("main")

app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description="AI-Powered Urban Land Record Harmonization Platform -- "
                 "Explainable GeoAI-assisted spatial data integration for urban cadastral records.",
    version=settings.APP_VERSION,
)

@app.on_event("startup")
def on_startup():
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} (demo_mode={settings.is_local_demo_mode}, free_demo_mode={settings.FREE_DEMO_MODE})")
    init_db()
    logger.info("Database initialized")
    # The hosted evaluator database is persistent, but Render instances can
    # sleep or restart. Ensure its deterministic fixture exists independently
    # of the opt-in local-demo setting; seed() is idempotent in free-demo mode.
    if settings.LOAD_SAMPLE_DATA or settings.FREE_DEMO_MODE:
        logger.info("Starting synthetic sample data seed (free_demo_mode=%s, load_sample_data=%s)",
                    settings.FREE_DEMO_MODE, settings.LOAD_SAMPLE_DATA)
        from run_seed import seed
        loaded = seed()
        logger.info("Synthetic sample data seed %s", "completed" if loaded else "skipped; already seeded")


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "tagline": "AI-Powered Urban Land Record Harmonization Platform",
        "docs": "/docs",
        "demo_mode": settings.is_local_demo_mode,
    }


api_auth = [Depends(current_user)]
app.include_router(system.router, prefix="/api", tags=["System"])
app.include_router(datasets.router, prefix="/api/datasets", tags=["Datasets"], dependencies=api_auth)
app.include_router(parcels.router, prefix="/api/parcels", tags=["Unified Parcels"], dependencies=api_auth)
app.include_router(harmonize.router, prefix="/api/harmonize", tags=["Harmonization Pipeline"], dependencies=api_auth)
app.include_router(matches.router, prefix="/api/matches", tags=["AI Spatial Matching"], dependencies=api_auth)
app.include_router(matches.mappings_router, prefix="/api/mappings", tags=["Attribute Mapping"], dependencies=api_auth)
app.include_router(conflicts.router, prefix="/api/conflicts", tags=["Conflict Detection"], dependencies=api_auth)
app.include_router(changes.router, prefix="/api/changes", tags=["Change Detection"], dependencies=api_auth)
app.include_router(statistics.router, prefix="/api/statistics", tags=["Statistics"], dependencies=api_auth)
app.include_router(statistics.quality_router, prefix="/api/data-quality", tags=["Data quality"], dependencies=api_auth)
app.include_router(export.router, prefix="/api/export", tags=["Export"], dependencies=api_auth)
app.include_router(pilot.router, prefix="/api/pilot", tags=["Pilot readiness"], dependencies=api_auth)
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication and audit"])

# Wrap the complete FastAPI application so CORS headers are also attached to
# unhandled-error responses produced by Starlette's outer ServerErrorMiddleware.
cors_origins = (
    [settings.FRONTEND_ORIGIN]
    if not settings.is_local_demo_mode
    else [settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"]
)
app = CORSMiddleware(
    app=app,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
