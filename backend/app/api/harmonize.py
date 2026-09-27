"""Harmonization pipeline endpoints: enqueue a run and inspect its status."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.orm import HarmonizationJob, User
from app.models.schemas import HarmonizationJobOut
from app.security import current_user, require_permission, write_audit
from app.services.harmonization_service import run_harmonization
from app.services.pilot_service import get_pilot_readiness
from app.services.free_demo import ensure_existing_capacity, require_job_type
from app.utils.ids import job_id

router = APIRouter()
settings = get_settings()


def _add_pilot_readiness_warning(db: Session, job: HarmonizationJob) -> None:
    readiness = get_pilot_readiness(db)
    if readiness["blocker_count"]:
        stages = list(job.stages or [])
        stages.append({
            "name": "Pilot Readiness Gate", "status": "warning", "processed": 0,
            "warnings": readiness["blocker_count"], "errors": 0,
            "detail": f"{readiness['blocker_count']} pilot blocker(s): outputs are for review/demo only.",
            "timestamp": datetime.utcnow().isoformat(),
        })
        job.stages = stages
        db.commit()


@router.post("", response_model=HarmonizationJobOut)
def trigger_harmonization(request: Request, db: Session = Depends(get_db),
                          user: User | None = Depends(current_user)):
    require_permission(user, "review")

    # Local SQLite demo and the explicitly bounded hosted demo use their
    # supported synchronous paths. Full production continues through Celery.
    if settings.is_local_demo_mode or settings.FREE_DEMO_MODE:
        if settings.FREE_DEMO_MODE:
            require_job_type("vector_harmonization", settings)
            ensure_existing_capacity(db, settings)
        job = run_harmonization(
            db,
            max_processing_seconds=(settings.FREE_DEMO_MAX_PROCESSING_SECONDS if settings.FREE_DEMO_MODE else None),
        )
        _add_pilot_readiness_warning(db, job)
        write_audit(db, user, "harmonization.started", "harmonization_job", job.id, request,
                    after={"status": job.status})
        write_audit(db, user, "harmonization.finished", "harmonization_job", job.id, request,
                    after={"status": job.status, "total_processed": job.total_processed})
        db.commit()
        db.refresh(job)
        return job

    job = HarmonizationJob(
        id=job_id(), status="queued", stages=[{
            "name": "Ingestion", "status": "pending", "processed": 0,
            "warnings": 0, "errors": 0, "detail": "Waiting for a harmonization worker.",
            "timestamp": datetime.utcnow().isoformat(),
        }], started_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    write_audit(db, user, "harmonization.queued", "harmonization_job", job.id, request,
                after={"status": "queued"})
    db.commit()
    db.refresh(job)

    try:
        from app.tasks import run_harmonization_job
        run_harmonization_job.delay(
            job.id,
            user.id if user else None,
            user.email if user else "system:api",
        )
    except Exception as error:
        db.rollback()
        job = db.query(HarmonizationJob).filter(HarmonizationJob.id == job.id).first()
        if job is not None:
            job.status = "failed"
            job.completed_at = datetime.utcnow()
            job.stages = [{
                "name": "Queue Error", "status": "failed", "processed": 0,
                "warnings": 0, "errors": 1,
                "detail": "Could not send the job to Redis. Check the Redis service and worker.",
                "timestamp": datetime.utcnow().isoformat(),
            }]
            write_audit(db, user, "harmonization.queue_failed", "harmonization_job", job.id,
                        request, after={"status": "failed", "error": str(error)})
            db.commit()
        raise HTTPException(status_code=503, detail="Harmonization worker queue is unavailable")

    db.refresh(job)
    return job


@router.get("/{job_id}", response_model=HarmonizationJobOut)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(HarmonizationJob).filter(HarmonizationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=list[HarmonizationJobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.query(HarmonizationJob).order_by(HarmonizationJob.started_at.desc()).limit(20).all()
