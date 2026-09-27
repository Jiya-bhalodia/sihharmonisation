import logging
import os
import tempfile
from datetime import datetime

from app.config import get_settings
from app.database import SessionLocal
from app.models.orm import AuditLog, Dataset
from app.queue import celery_app
from app.utils.ids import new_id

logger = logging.getLogger("bhumix.imagery")


@celery_app.task(name="app.tasks.inspect_raster_asset", bind=True, max_retries=3,
                 autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True)
def inspect_raster_asset(self, dataset_id: str, object_key: str,
                         auto_harmonization_job_id: str | None = None):
    """Inspect a stored GeoTIFF/COG asynchronously; originals stay in object storage."""
    settings = get_settings()
    db = SessionLocal()
    try:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if dataset is None:
            return {"status": "missing", "dataset_id": dataset_id}
        dataset.status = "processing"
        db.commit()
        import boto3
        client = boto3.client(
            "s3", endpoint_url=settings.OBJECT_STORAGE_ENDPOINT or None,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY or None,
            region_name=os.getenv("AWS_DEFAULT_REGION") or None,
        )
        with tempfile.TemporaryDirectory(prefix="bhumix-raster-") as temp_dir:
            local_path = f"{temp_dir}/source.tif"
            client.download_file(settings.OBJECT_STORAGE_BUCKET, object_key, local_path)
            from app.services.format_service import ingest_raster
            ingest_raster(db, None, dataset.name, dataset.department, dataset.source_type,
                          dataset_id=dataset.id, file_path=local_path)
        db.add(AuditLog(id=new_id("AU"), actor_email="system:imagery-worker",
                        action="dataset.raster_processed", resource_type="dataset",
                        resource_id=dataset_id, before_state={"status": "processing"},
                        after_state={"status": "uploaded"}, created_at=datetime.utcnow()))
        db.commit()
        if auto_harmonization_job_id:
            from app.services.auto_harmonization import dispatch_auto_job
            dispatch_auto_job(db, auto_harmonization_job_id)
        return {"status": "completed", "dataset_id": dataset_id}
    except Exception as error:
        db.rollback()
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if dataset:
            dataset.status = "error"
            db.add(AuditLog(id=new_id("AU"), actor_email="system:imagery-worker",
                            action="dataset.raster_processing_failed", resource_type="dataset",
                            resource_id=dataset_id, after_state={"status": "error"},
                            created_at=datetime.utcnow()))
            db.commit()
        if auto_harmonization_job_id and self.request.retries >= self.max_retries:
            from app.models.orm import HarmonizationJob
            pending_job = db.query(HarmonizationJob).filter(
                HarmonizationJob.id == auto_harmonization_job_id
            ).first()
            if pending_job:
                pending_job.status = "failed"
                pending_job.completed_at = datetime.utcnow()
                pending_job.stages = list(pending_job.stages or []) + [{
                    "name": "Raster Ingestion", "status": "failed", "processed": 0,
                    "warnings": 0, "errors": 1,
                    "detail": "Raster processing failed; automatic harmonization was not run.",
                    "timestamp": datetime.utcnow().isoformat(),
                }]
                db.commit()
        logger.exception("Raster processing failed for %s", dataset_id)
        raise error
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_harmonization_job")
def run_harmonization_job(job_id: str, actor_user_id: str | None = None,
                          actor_email: str | None = None):
    """Run a queued harmonization job outside the API request."""
    from app.models.orm import HarmonizationJob
    from app.services.harmonization_service import run_harmonization
    from app.services.pilot_service import get_pilot_readiness

    db = SessionLocal()
    try:
        job = run_harmonization(db, existing_job_id=job_id)
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

        db.add(AuditLog(
            id=new_id("AU"), actor_user_id=actor_user_id,
            actor_email=actor_email or "system:harmonization-worker",
            action="harmonization.finished" if job.status == "completed" else "harmonization.failed",
            resource_type="harmonization_job", resource_id=job.id,
            after_state={"status": job.status, "total_processed": job.total_processed},
            created_at=datetime.utcnow(),
        ))
        db.commit()
        return {"job_id": job.id, "status": job.status}
    except Exception as error:
        db.rollback()
        job = db.query(HarmonizationJob).filter(HarmonizationJob.id == job_id).first()
        if job is not None:
            job.status = "failed"
            job.completed_at = datetime.utcnow()
            stages = list(job.stages or [])
            stages.append({
                "name": "Pipeline Error", "status": "failed", "processed": 0,
                "warnings": 0, "errors": 1, "detail": str(error),
                "timestamp": datetime.utcnow().isoformat(),
            })
            job.stages = stages
            db.add(AuditLog(
                id=new_id("AU"), actor_user_id=actor_user_id,
                actor_email=actor_email or "system:harmonization-worker",
                action="harmonization.failed", resource_type="harmonization_job",
                resource_id=job.id, after_state={"status": "failed", "error": str(error)},
                created_at=datetime.utcnow(),
            ))
            db.commit()
        logger.exception("Queued harmonization job %s failed", job_id)
        raise
    finally:
        db.close()
