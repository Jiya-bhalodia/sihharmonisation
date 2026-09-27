"""
Seeds the BHUMI-X database with the generated sample datasets.

Usage (from backend/ directory, after running scripts/generate_sample_data.py
from the project root):

    python run_seed.py

By default, this only seeds an empty database and preserves existing data.
Pass --reset to clear and recreate all tables. It ingests every file in
data/sample/ as a distinct dataset attributed to a plausible department,
exactly as an end user would via the Data Sources upload page -- so the
seeded state is 100% reproducible through the same ingestion code path
used by the API.
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from app.database import Base, engine, SessionLocal, init_db
from app.models.orm import Dataset
from app.services.dataset_service import ingest_geojson_dict
from app.services.change_service import save_snapshot
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger("run_seed")
settings = get_settings()

SAMPLE_DIR = os.environ.get("SAMPLE_DATA_DIR", os.path.join(os.path.dirname(__file__), settings.DATA_DIR, "sample"))
SAMPLE_DIR = os.path.abspath(SAMPLE_DIR)

DATASET_DEFINITIONS = [
    {"file": "cadastral_parcels.geojson", "name": "[Synthetic / Illustrative] Cadastral Parcels - Ward 07",
     "department": "Survey Department", "source_type": "cadastral"},
    {"file": "revenue_records.geojson", "name": "[Synthetic / Illustrative] Revenue Land Records - Ward 07",
     "department": "Revenue Department", "source_type": "revenue"},
    {"file": "municipal_buildings.geojson", "name": "[Synthetic / Illustrative] Municipal Building Register",
     "department": "Municipal Corporation", "source_type": "municipal"},
    {"file": "ground_truth_points.geojson", "name": "[Synthetic / Illustrative] Field Verification Points",
     "department": "Ground Truthing Team", "source_type": "ground_truth"},
    {"file": "utility_lines.geojson", "name": "[Synthetic / Illustrative] Utility Network (Water/Power/Sewer)",
     "department": "Utility Department", "source_type": "utility"},
]


def seed(reset=False):
    if reset:
        print("Reset requested: dropping and recreating all tables...")
        Base.metadata.drop_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        if not reset and db.query(Dataset).count():
            print("Sample seed skipped: datasets already exist; existing database was left unchanged.")
            return False
        if not os.path.isdir(SAMPLE_DIR):
            raise RuntimeError(f"Sample data directory not found: {SAMPLE_DIR}")
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
                    name="[Synthetic / Illustrative] GNSS/CORS Survey Points - Ward 07",
                    department="Survey Department",
                    source_type="gnss",
                )
            print(f"  Ingested {ds.name}: {ds.feature_count} features (quality {ds.quality_score}%)")

        # Hosted free instances have no durable local filesystem, so do not
        # create a snapshot or imply snapshot-based change detection there.
        if not settings.FREE_DEMO_MODE:
            save_snapshot(db)
        from app.services.harmonization_service import run_harmonization
        from app.services.change_service import detect_changes
        job = run_harmonization(
            db,
            max_processing_seconds=(settings.FREE_DEMO_MAX_PROCESSING_SECONDS if settings.FREE_DEMO_MODE else None),
        )
        if job.status == "completed" and not settings.FREE_DEMO_MODE:
            detect_changes(db, job.id)
        print(f"\nSeed complete; harmonization status: {job.status}.")
        print("To demo Change Detection: upload data/sample/drone_buildings_v2.geojson as a new")
        print("'municipal' dataset via Data Sources, then re-run harmonization.")
        return True
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load synthetic BHUMI-X sample data")
    parser.add_argument("--reset", action="store_true", help="destructively clear all tables before seeding")
    seed(reset=parser.parse_args().reset)
