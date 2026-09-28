"""
Dataset ingestion endpoints: list datasets and upload new ones
(GeoJSON, CSV with lat/lon, or Shapefile ZIP).

Security fix (senior review): enforce a maximum upload size at the API
boundary, before any parsing is attempted, to prevent memory-exhaustion
from an oversized upload.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.schemas import DatasetOut
from app.models.orm import Dataset, AttributeMapping
from app.services import dataset_service
from app.config import get_settings
from app.utils.logger import get_logger
from app.models.orm import User
from app.security import current_user, require_permission, write_audit
from app.object_storage import store_original, store_original_stream
from app.services.free_demo import ensure_dataset_capacity, preflight_upload
from app.utils.ids import new_id
from datetime import datetime
from starlette.concurrency import run_in_threadpool
import csv
import io
import json

router = APIRouter()
logger = get_logger("api.datasets")
settings = get_settings()

ALLOWED_EXTENSIONS = (".geojson", ".json", ".csv", ".zip", ".kml", ".kmz", ".tif", ".tiff", ".pdf")
VALID_SOURCE_TYPES = {"cadastral", "revenue", "municipal", "gnss", "ground_truth", "utility", "land_use", "drone", "orthoimagery", "dsm", "dtm"}


@router.get("", response_model=List[DatasetOut])
def get_datasets(db: Session = Depends(get_db)):
    return dataset_service.list_datasets(db)


@router.post("/upload", response_model=DatasetOut)
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    department: str = Form(...),
    source_type: str = Form(...),
    lat_field: str = Form("latitude"),
    lon_field: str = Form("longitude"),
    public_demo_approved: bool = Form(False),
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    if source_type != "auto" and source_type not in VALID_SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"source_type must be one of {sorted(VALID_SOURCE_TYPES)} or auto")
    if settings.FREE_DEMO_MODE and not public_demo_approved:
        raise HTTPException(status_code=422, detail=(
            "Confirm that this upload contains synthetic/illustrative data or is approved for public SIH evaluation."
        ))

    filename = (file.filename or "").lower().strip()
    if not filename or not filename.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400,
                             detail=f"Unsupported file type. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}")

    file.file.seek(0, 2)
    upload_size = file.file.tell()
    file.file.seek(0)
    if upload_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    upload_limit_mb = settings.FREE_DEMO_MAX_UPLOAD_MB if settings.FREE_DEMO_MODE else settings.MAX_UPLOAD_SIZE_MB
    max_bytes = upload_limit_mb * 1024 * 1024
    if upload_size > max_bytes:
        raise HTTPException(status_code=413,
                             detail=f"File exceeds the {upload_limit_mb} MB upload limit")

    free_demo_content = None
    if settings.FREE_DEMO_MODE:
        free_demo_content = await file.read()
        try:
            added_features, added_complexity = preflight_upload(file.filename or filename, free_demo_content)
            ensure_dataset_capacity(db, added_features, added_complexity)
        finally:
            await file.seek(0)

    classification = None
    if source_type == "auto":
        # Use only the filename, user-provided name, and schema keys. Never inspect
        # feature values to guess a department or land-record category.
        fields = []
        if filename.endswith(".csv"):
            try:
                header = file.file.readline(64 * 1024).decode("utf-8-sig", errors="replace")
                fields = next(csv.reader(io.StringIO(header)), [])
            finally:
                file.file.seek(0)
        elif filename.endswith((".json", ".geojson")) and upload_size <= 5 * 1024 * 1024:
            try:
                payload = json.loads(file.file.read().decode("utf-8"))
                features = payload.get("features", []) if isinstance(payload, dict) else []
                if features and isinstance(features[0], dict):
                    fields = list((features[0].get("properties") or {}).keys())
            except (ValueError, UnicodeDecodeError):
                fields = []
            finally:
                file.file.seek(0)
        from app.services.source_classifier import classify_source_type
        classification = classify_source_type(name, filename, fields)
        source_type = classification.get("source_type")
        if not source_type or classification.get("confidence", 0) < 0.6:
            raise HTTPException(status_code=422, detail={
                "message": "Could not confidently infer the dataset type from its name and fields. Select it manually.",
                "suggestion": classification,
            })
    require_permission(user, f"upload:{source_type}")

    if settings.FREE_DEMO_MODE and source_type in {"orthoimagery", "dsm", "dtm"}:
        raise HTTPException(status_code=422, detail=(
            "Unavailable in the hosted evaluation demo: raster and surface-model inputs are disabled. "
            "Use a small CSV or GeoJSON vector dataset instead."
        ))

    raster_ext = filename.endswith((".tif", ".tiff"))
    async_threshold = settings.ASYNC_RASTER_THRESHOLD_MB * 1024 * 1024
    run_local_building_models = (
        settings.BUILDING_EXTRACTION_ENABLED and source_type in {"drone", "orthoimagery"}
    )
    if raster_ext and not settings.is_local_demo_mode and (upload_size >= async_threshold or run_local_building_models):
        dataset = Dataset(id=new_id("DS"), name=name, department=department,
                          source_type=source_type, geometry_type="Raster footprint",
                          crs=None, feature_count=0, quality_score=0.0,
                          status="processing", uploaded_at=datetime.utcnow())
        db.add(dataset)
        db.flush()
        auto_job = None
        try:
            dataset.file_path = await run_in_threadpool(store_original_stream, dataset.id, file.filename or filename, file.file)
            object_key = dataset.file_path.split(f"s3://{settings.OBJECT_STORAGE_BUCKET}/", 1)[1]
            write_audit(db, user, "dataset.raster_queued", "dataset", dataset.id, request,
                        after={"name": dataset.name, "source_type": source_type,
                               "classification": classification, "bytes": upload_size})
            db.commit()
            db.refresh(dataset)
        except Exception as error:
            db.rollback()
            logger.error(f"Could not queue raster dataset: {error}")
            raise HTTPException(status_code=503, detail="Raster processing queue is unavailable")
        try:
            from app.services.auto_harmonization import create_auto_job
            auto_job = create_auto_job(
                db, user.id if user else None,
                user.email if user else "system:auto-harmonization",
                waiting_for_raster=True,
            )
            from app.tasks import inspect_raster_asset
            inspect_raster_asset.delay(dataset.id, object_key, auto_job.id)
        except Exception as error:
            dataset.status = "error"
            write_audit(db, user, "dataset.raster_queue_failed", "dataset", dataset.id, request,
                        after={"status": "error"})
            db.commit()
            if auto_job is not None:
                from app.models.orm import HarmonizationJob
                queued_job = db.query(HarmonizationJob).filter(HarmonizationJob.id == auto_job.id).first()
                if queued_job:
                    queued_job.status = "failed"
                    queued_job.completed_at = datetime.utcnow()
                    queued_job.stages = list(queued_job.stages or []) + [{
                        "name": "Raster Queue", "status": "failed", "processed": 0,
                        "warnings": 0, "errors": 1,
                        "detail": "Raster upload could not be queued; harmonization was not run.",
                        "timestamp": datetime.utcnow().isoformat(),
                    }]
                    db.commit()
            logger.error(f"Could not enqueue raster dataset {dataset.id}: {error}")
            raise HTTPException(status_code=503, detail="Raster processing queue is unavailable")
        return dataset

    contents = free_demo_content if free_demo_content is not None else await file.read()
    try:
        if filename.endswith(".geojson") or filename.endswith(".json"):
            dataset = dataset_service.ingest_geojson_file(db, contents, name, department, source_type)
        elif filename.endswith(".csv"):
            dataset = dataset_service.ingest_csv_latlon(db, contents, name, department, source_type,
                                                          lat_field=lat_field, lon_field=lon_field)
        elif filename.endswith(".zip"):
            dataset = dataset_service.ingest_shapefile_zip(db, contents, name, department, source_type)
        elif filename.endswith(".kml") or filename.endswith(".kmz"):
            from app.services.format_service import ingest_kml_or_kmz
            dataset = ingest_kml_or_kmz(db, contents, filename, name, department, source_type)
        elif filename.endswith(".tif") or filename.endswith(".tiff"):
            from app.services.format_service import ingest_raster
            dataset = ingest_raster(db, contents, name, department, source_type)
        elif filename.endswith(".pdf"):
            from app.services.format_service import ingest_pdf
            dataset = ingest_pdf(db, contents, name, department, source_type)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Upload rejected for {filename}: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Upload failed for {filename}: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to parse uploaded file: {str(e)}")

    try:
        dataset.file_path = store_original(dataset.id, filename, contents)
    except Exception as error:
        db.delete(dataset)
        db.commit()
        logger.error(f"Original file storage failed for dataset {dataset.id}: {error}")
        raise HTTPException(status_code=503, detail="Original file could not be stored")
    write_audit(db, user, "dataset.uploaded", "dataset", dataset.id, request,
                after={"name": dataset.name, "source_type": dataset.source_type,
                       "classification": classification, "department": dataset.department,
                       "feature_count": dataset.feature_count})
    db.commit()
    try:
        from app.services.auto_harmonization import create_auto_job
        create_auto_job(db, user.id if user else None,
                        user.email if user else "system:auto-harmonization")
    except Exception as error:
        # Preserve the successfully uploaded source and surface pipeline errors
        # through the harmonization jobs view.
        logger.exception("Dataset %s uploaded, but automatic harmonization failed: %s", dataset.id, error)
    return dataset


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, request: Request, db: Session = Depends(get_db),
                   user: User | None = Depends(current_user)):
    require_permission(user, "datasets:delete")
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    before = {"name": dataset.name, "source_type": dataset.source_type,
              "department": dataset.department, "feature_count": dataset.feature_count}
    db.query(AttributeMapping).filter(AttributeMapping.dataset_id == dataset_id).delete()
    db.delete(dataset)
    write_audit(db, user, "dataset.deleted", "dataset", dataset_id, request, before=before)
    db.commit()
    return {"status": "deleted", "id": dataset_id}
