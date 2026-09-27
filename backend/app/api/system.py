"""System liveness and dependency readiness endpoints."""
from datetime import datetime
import os

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.config import get_settings
from app.database import engine

router = APIRouter()
settings = get_settings()
START_TIME = datetime.utcnow()


@router.get("/health")
def health_check():
    free_demo = settings.FREE_DEMO_MODE
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "demo_mode": settings.is_local_demo_mode,
        "free_demo_mode": free_demo,
        "disabled_features": ([
            "celery_jobs", "raster_processing", "building_detection", "segmentation",
            "local_embeddings", "local_llm", "pdf_ocr", "snapshot_change_detection",
        ] if free_demo else []),
        "free_demo_limits": ({
            "max_upload_mb": settings.FREE_DEMO_MAX_UPLOAD_MB,
            "max_datasets": settings.FREE_DEMO_MAX_DATASETS,
            "max_features": settings.FREE_DEMO_MAX_FEATURES,
            "max_geometry_complexity": settings.FREE_DEMO_MAX_GEOMETRY_COMPLEXITY,
            "max_processing_seconds": settings.FREE_DEMO_MAX_PROCESSING_SECONDS,
        } if free_demo else None),
        "uptime_seconds": (datetime.utcnow() - START_TIME).total_seconds(),
        "database": "SQLite (Local Demo Mode)" if settings.is_local_demo_mode else "PostgreSQL + PostGIS",
        "target_crs": settings.TARGET_CRS,
    }


@router.get("/ready")
def readiness_check():
    """Check only dependencies needed by the selected runtime profile."""
    if settings.is_local_demo_mode:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"status": "ready", "checks": {"database": True}}
        except Exception:
            raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": {"database": False}})

    checks = {"postgres_postgis": False, "redis": False, "object_storage": False}
    try:
        schema = settings.POSTGIS_SCHEMA
        with engine.connect() as connection:
            connection.execute(text(f'SELECT "{schema}".postgis_version()'))
            geometry_type_exists = connection.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE t.typname = 'geometry' AND n.nspname = :schema)"
            ), {"schema": schema}).scalar()
        checks["postgres_postgis"] = bool(geometry_type_exists)
    except Exception:
        pass

    redis_client = None
    try:
        from redis import Redis
        redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, socket_timeout=3)
        checks["redis"] = bool(redis_client.ping())
    except Exception:
        pass
    finally:
        if redis_client is not None:
            redis_client.close()

    try:
        import boto3
        from botocore.config import Config
        object_store = boto3.client(
            "s3",
            endpoint_url=settings.OBJECT_STORAGE_ENDPOINT or None,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY or None,
            region_name=os.getenv("AWS_DEFAULT_REGION") or None,
            config=Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 1}),
        )
        object_store.head_bucket(Bucket=settings.OBJECT_STORAGE_BUCKET)
        checks["object_storage"] = True
    except Exception:
        pass

    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}
