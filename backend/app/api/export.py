"""
Export endpoints for the unified land record: GeoJSON and CSV.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.export_service import export_geojson, export_csv
from app.models.orm import User
from app.security import current_user, require_permission, write_audit

router = APIRouter()


@router.get("/geojson")
def get_export_geojson(request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    require_permission(user, "export")
    data = export_geojson(db)
    write_audit(db, user, "records.exported.geojson", "export", None, request)
    db.commit()
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": "attachment; filename=bhumix_unified_land_records.geojson"},
    )


@router.get("/csv")
def get_export_csv(request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    require_permission(user, "export")
    csv_text = export_csv(db)
    write_audit(db, user, "records.exported.csv", "export", None, request)
    db.commit()
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bhumix_unified_land_records.csv"},
    )
