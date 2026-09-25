"""
Export endpoints for the unified land record: GeoJSON and CSV.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.export_service import export_geojson, export_csv

router = APIRouter()


@router.get("/geojson")
def get_export_geojson(db: Session = Depends(get_db)):
    data = export_geojson(db)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": "attachment; filename=bhumix_unified_land_records.geojson"},
    )


@router.get("/csv")
def get_export_csv(db: Session = Depends(get_db)):
    csv_text = export_csv(db)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bhumix_unified_land_records.csv"},
    )