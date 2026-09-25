"""
Seeds the BHUMI-X database with the generated sample datasets.

Usage (from backend/ directory, after running scripts/generate_sample_data.py
from the project root):

    python run_seed.py

This clears and recreates all tables, then ingests every file in
data/sample/ as a distinct dataset attributed to a plausible department,
exactly as an end user would via the Data Sources upload page -- so the
seeded state is 100% reproducible through the same ingestion code path
used by the API.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

from app.database import Base, engine, SessionLocal, init_db
from app.services.dataset_service import ingest_geojson_dict
from app.services.change_service import save_snapshot
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger("run_seed")
settings = get_settings()

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), settings.DATA_DIR, "sample")
SAMPLE_DIR = os.path.abspath(SAMPLE_DIR)

DATASET_DEFINITIONS = [
    {"file": "cadastral_parcels.geojson", "name": "Cadastral Parcels - Ward 07",
     "department": "Survey Department", "source_type": "cadastral"},
    {"file": "revenue_records.geojson", "name": "Revenue Land Records - Ward 07",
     "department": "Revenue Department", "source_type": "revenue"},
    {"file": "municipal_buildings.geojson", "name": "Municipal Building Register",
     "department": "Municipal Corporation", "source_type": "municipal"},
    {"file": "ground_truth_points.geojson", "name": "Field Verification Points",
     "department": "Ground Truthing Team", "source_type": "ground_truth"},
    {"file": "utility_lines.geojson", "name": "Utility Network (Water/Power/Sewer)",
     "department": "Utility Department", "source_type": "utility"},
]


def seed():
    print("Dropping and recreating all tables...")
    Base.metadata.drop_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        for definition in DATASET_DEFINITIONS:
            path = os.path.join(SAMPLE_DIR, definition["file"])
            if not os.path.exists(path):
                print(f"  SKIP (not found): {path}")
                continue
            with open(path, "r") as f:
                geojson = json.load(f)
            ds = ingest_geojson_dict(
                db, geojson,
                name=definition["name"],
                department=definition["department"],
                source_type=definition["source_type"],
            )
            print(f"  Ingested {ds.name}: {ds.feature_count} features (quality {ds.quality_score}%)")

        # GNSS points come from CSV
        gnss_csv_path = os.path.join(SAMPLE_DIR, "gnss_survey_points.csv")
        if os.path.exists(gnss_csv_path):
            from app.services.dataset_service import ingest_csv_latlon
            with open(gnss_csv_path, "rb") as f:
                ds = ingest_csv_latlon(
                    db, f.read(),
                    name="GNSS/CORS Survey Points - Ward 07",
                    department="Survey Department",
                    source_type="gnss",
                )
            print(f"  Ingested {ds.name}: {ds.feature_count} features (quality {ds.quality_score}%)")

        # Save an initial empty-ish snapshot so the FIRST harmonization run
        # shows "all new" and the SECOND run (after drone v2 is loaded)
        # shows genuine change detection.
        save_snapshot(db)
        print("\nSeed complete. Run the harmonization pipeline via POST /api/harmonize or the frontend.")
        print("To demo Change Detection: upload data/sample/drone_buildings_v2.geojson as a new")
        print("'municipal' dataset via Data Sources, then re-run harmonization.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()