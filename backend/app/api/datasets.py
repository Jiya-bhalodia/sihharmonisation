"""
Dataset ingestion endpoints: list datasets and upload new ones
(GeoJSON, CSV with lat/lon, or Shapefile ZIP).

Security fix (senior review): enforce a maximum upload size at the API
boundary, before any parsing is attempted, to prevent memory-exhaustion
from an oversized upload.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.schemas import DatasetOut
from app.models.orm import Dataset, AttributeMapping
from app.services import dataset_service
from app.config import get_settings
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger("api.datasets")
settings = get_settings()

ALLOWED_EXTENSIONS = (".geojson", ".json", ".csv", ".zip", ".kml", ".kmz", ".tif", ".tiff", ".pdf")
VALID_SOURCE_TYPES = {"cadastral", "revenue", "municipal", "gnss", "ground_truth", "utility", "drone", "orthoimagery", "dsm", "dtm"}


@router.get("", response_model=List[DatasetOut])
def get_datasets(db: Session = Depends(get_db)):
    return dataset_service.list_datasets(db)


@router.post("/upload", response_model=DatasetOut)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(...),
    department: str = Form(...),
    source_type: str = Form(...),
    lat_field: str = Form("latitude"),
    lon_field: str = Form("longitude"),
    db: Session = Depends(get_db),
):
    if source_type not in VALID_SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}")

    filename = (file.filename or "").lower().strip()
    if not filename or not filename.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400,
                             detail=f"Unsupported file type. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}")

    contents = await file.read()

    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(status_code=413,
                             detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit")

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

    return dataset


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    db.query(AttributeMapping).filter(AttributeMapping.dataset_id == dataset_id).delete()
    db.delete(dataset)
    db.commit()
    return {"status": "deleted", "id": dataset_id}
