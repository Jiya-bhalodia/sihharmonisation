"""Start a reviewable harmonization run after newly ingested data is committed."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.orm import AuditLog, HarmonizationJob
from app.services.free_demo import ensure_existing_capacity, require_job_type
from app.utils.ids import job_id, new_id


def create_auto_job(db: Session, actor_user_id: str | None = None,
                    actor_email: str = "system:auto-harmonization",
                    waiting_for_raster: bool = False) -> HarmonizationJob:
    """In demo mode run synchronously; production creates a durable queue record."""
    settings = get_settings()
    if (settings.is_local_demo_mode or settings.FREE_DEMO_MODE) and not waiting_for_raster:
        if settings.FREE_DEMO_MODE:
            require_job_type("vector_harmonization", settings)
            ensure_existing_capacity(db, settings)
        from app.services.harmonization_service import run_harmonization
        return run_harmonization(
            db,
            max_processing_seconds=(settings.FREE_DEMO_MAX_PROCESSING_SECONDS if settings.FREE_DEMO_MODE else None),
        )

    if settings.FREE_DEMO_MODE and waiting_for_raster:
        raise ValueError("Raster processing is unavailable in the hosted evaluation demo.")

    detail = "Waiting for raster processing before harmonization." if waiting_for_raster else "Queued after dataset upload."
    job = HarmonizationJob(
        id=job_id(), status="queued", stages=[{
            "name": "Ingestion", "status": "pending", "processed": 0,
            "warnings": 0, "errors": 0, "detail": detail,
            "timestamp": datetime.utcnow().isoformat(),
        }], started_at=datetime.utcnow(),
    )
    db.add(job)
    db.add(AuditLog(
        id=new_id("AU"), actor_user_id=actor_user_id, actor_email=actor_email,
        action="harmonization.auto_queued", resource_type="harmonization_job",
        resource_id=job.id, after_state={"status": "queued", "trigger": "dataset_upload"},
        created_at=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(job)
    if not waiting_for_raster:
        dispatch_auto_job(db, job.id, actor_user_id, actor_email)
    return job


def dispatch_auto_job(db: Session, auto_job_id: str, actor_user_id: str | None = None,
                      actor_email: str = "system:auto-harmonization") -> None:
    """Dispatch a queued job; record queue failures without undoing the upload."""
    try:
        from app.tasks import run_harmonization_job
        run_harmonization_job.delay(auto_job_id, actor_user_id, actor_email)
    except Exception as error:
        db.rollback()
        job = db.query(HarmonizationJob).filter(HarmonizationJob.id == auto_job_id).first()
        if job:
            job.status = "failed"
            job.completed_at = datetime.utcnow()
            job.stages = list(job.stages or []) + [{
                "name": "Queue Error", "status": "failed", "processed": 0,
                "warnings": 0, "errors": 1,
                "detail": "Upload succeeded, but automatic harmonization could not be queued. Check Redis and the worker.",
                "timestamp": datetime.utcnow().isoformat(),
            }]
            db.add(AuditLog(
                id=new_id("AU"), actor_user_id=actor_user_id, actor_email=actor_email,
                action="harmonization.auto_queue_failed", resource_type="harmonization_job",
                resource_id=job.id, after_state={"status": "failed", "error": str(error)[:500]},
                created_at=datetime.utcnow(),
            ))
            db.commit()
