"""
Harmonization pipeline endpoints: trigger a run and check job status.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models.orm import HarmonizationJob
from app.models.schemas import HarmonizationJobOut
from app.services.harmonization_service import run_harmonization
from app.services.change_service import detect_changes
from app.services.pilot_service import get_pilot_readiness

router = APIRouter()


@router.post("", response_model=HarmonizationJobOut)
def trigger_harmonization(db: Session = Depends(get_db)):
    job = run_harmonization(db)
    readiness = get_pilot_readiness(db)
    if readiness["blocker_count"]:
        # Keep demonstration workflows usable, but do not let a run look like
        # a legally-ready pilot when its technical prerequisites are absent.
        stages = list(job.stages or [])
        stages.append({
            "name": "Pilot Readiness Gate", "status": "warning", "processed": 0,
            "warnings": readiness["blocker_count"], "errors": 0,
            "detail": f"{readiness['blocker_count']} pilot blocker(s): outputs are for review/demo only.",
            "timestamp": datetime.utcnow().isoformat(),
        })
        job.stages = stages
        db.commit()
        db.refresh(job)
    if job.status == "completed":
        detect_changes(db, job.id)
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
