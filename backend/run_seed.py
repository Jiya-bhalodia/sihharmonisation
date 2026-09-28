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
import csv
import io

sys.path.insert(0, os.path.dirname(__file__))

from app.database import Base, engine, SessionLocal, init_db
from app.models.orm import Dataset, HarmonizationJob
from app.services.dataset_service import ingest_geojson_dict
from app.services.change_service import save_snapshot
from app.config import get_settings
from app.sample_data import get_sample_data_dir
from app.utils.logger import get_logger
from sqlalchemy import text
from shapely.geometry import shape

logger = get_logger("run_seed")
settings = get_settings()

SAMPLE_DIR = str(get_sample_data_dir())

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
    {"file": "land_use.geojson", "name": "[Synthetic / Illustrative] Land Use Inventory - Ward 07",
     "department": "Municipal Corporation", "source_type": "land_use"},
]

# Keep hosted Postgres work comfortably inside its synchronous processing
# budget while drawing every shape/property from the checked-in demo fixtures.
HOSTED_DEMO_PARCEL_IDS = {f"P-{number:04d}" for number in range(101, 132)}


def _hosted_demo_geojson(geojson, source_type):
    features = geojson.get("features", [])
    if source_type == "cadastral":
        selected = [feature for feature in features
                    if (feature.get("properties") or {}).get("parcel_id") in HOSTED_DEMO_PARCEL_IDS]
        # Keep the fixture's deliberate invalid polygon so validation and
        # correction are visible in the real topology output.
        selected.extend(feature for feature in features
                        if not (feature.get("properties") or {}).get("parcel_id") in HOSTED_DEMO_PARCEL_IDS
                        and feature.get("geometry") and len(selected) < 32
                        and not shape(feature["geometry"]).is_valid)
        return {**geojson, "features": selected}
    if source_type == "revenue":
        features = [feature for feature in features
                    if (feature.get("properties") or {}).get("survey_no") in HOSTED_DEMO_PARCEL_IDS]
    elif source_type == "municipal":
        features = [feature for feature in features
                    if (feature.get("properties") or {}).get("linked_parcel") in HOSTED_DEMO_PARCEL_IDS]
    elif source_type in {"ground_truth", "land_use"}:
        features = [feature for feature in features
                    if (feature.get("properties") or {}).get("parcel_id") in HOSTED_DEMO_PARCEL_IDS]
    elif source_type == "utility":
        features = features[:12]
    return {**geojson, "features": features}


def _hosted_demo_gnss_csv(content):
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    selected = [row for row in rows if row.get("linked_parcel_id") in HOSTED_DEMO_PARCEL_IDS]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys() if rows else [])
    if rows:
        writer.writeheader()
        writer.writerows(selected)
    return output.getvalue().encode("utf-8")


def seed(reset=False):
    if reset:
        print("Reset requested: dropping and recreating all tables...")
        Base.metadata.drop_all(bind=engine)
    init_db()

    db = SessionLocal()
    advisory_lock = False
    try:
        # Serialize startup across multiple Render instances. PostgreSQL
        # session advisory locks survive the commits performed by ingestion.
        if settings.FREE_DEMO_MODE and db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_lock(26013, 2026)"))
            advisory_lock = True
        if not reset and not settings.FREE_DEMO_MODE and db.query(Dataset).count():
            print("Sample seed skipped: datasets already exist; existing database was left unchanged.")
            return False
        if not os.path.isdir(SAMPLE_DIR):
            raise RuntimeError(f"Sample data directory not found: {SAMPLE_DIR}")
        added_dataset = False
        for definition in DATASET_DEFINITIONS:
            path = os.path.join(SAMPLE_DIR, definition["file"])
            if not os.path.exists(path):
                print(f"  SKIP (not found): {path}")
                continue
            # Stable dataset names are the hosted-demo fixture keys. Resume a
            # partially completed seed without duplicating already ingested
            # sources, and leave unrelated user datasets untouched.
            existing = db.query(Dataset).filter(Dataset.name == definition["name"]).first()
            if existing:
                continue
            with open(path, "r") as f:
                geojson = json.load(f)
            if settings.FREE_DEMO_MODE:
                geojson = _hosted_demo_geojson(geojson, definition["source_type"])
            ds = ingest_geojson_dict(
                db, geojson,
                name=definition["name"],
                department=definition["department"],
                source_type=definition["source_type"],
                provenance="synthetic_demo",
            )
            added_dataset = True
            print(f"  Ingested {ds.name}: {ds.feature_count} features (quality {ds.quality_score}%)")

        # GNSS points come from CSV
        gnss_csv_path = os.path.join(SAMPLE_DIR, "gnss_survey_points.csv")
        gnss_name = "[Synthetic / Illustrative] GNSS/CORS Survey Points - Ward 07"
        if os.path.exists(gnss_csv_path) and not db.query(Dataset).filter(Dataset.name == gnss_name).first():
            from app.services.dataset_service import ingest_csv_latlon
            with open(gnss_csv_path, "rb") as f:
                ds = ingest_csv_latlon(
                    db, _hosted_demo_gnss_csv(f.read()) if settings.FREE_DEMO_MODE else f.read(),
                    name=gnss_name,
                    department="Survey Department",
                    source_type="gnss",
                    provenance="synthetic_demo",
            )
            added_dataset = True
            print(f"  Ingested {ds.name}: {ds.feature_count} features (quality {ds.quality_score}%)")

        # Hosted free instances have no durable local filesystem, so do not
        # create a snapshot or imply snapshot-based change detection there.
        if not settings.FREE_DEMO_MODE:
            save_snapshot(db)
        latest_job = db.query(HarmonizationJob).order_by(HarmonizationJob.started_at.desc()).first()
        if settings.FREE_DEMO_MODE and not added_dataset and latest_job and latest_job.status == "completed":
            print("Hosted demo fixtures and harmonization outputs are already present.")
            return False
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
        if advisory_lock:
            try:
                db.execute(text("SELECT pg_advisory_unlock(26013, 2026)"))
            except Exception:
                pass
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load synthetic BHUMI-X sample data")
    parser.add_argument("--reset", action="store_true", help="destructively clear all tables before seeding")
    seed(reset=parser.parse_args().reset)
