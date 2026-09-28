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
from app.models.orm import (
    AttributeMapping, Dataset, Feature, HarmonizationJob,
    MatchRecord, UnifiedParcel, ValidationResult,
)
from app.services.dataset_service import ingest_geojson_dict
from app.services.change_service import save_snapshot
from app.config import get_settings
from app.sample_data import get_sample_data_dir
from app.utils.logger import get_logger
from sqlalchemy import func, text
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
# Keep ten GNSS-linked parcels in the hosted subset: pilot readiness requires
# ten observations, and bounding other parcel candidates reduces the
# synchronous GNSS-outside-parcel comparisons on the Render Free instance.
HOSTED_DEMO_PARCEL_IDS = {
    "P-0103", "P-0109", "P-0113", "P-0115", "P-0116",
    "P-0117", "P-0118", "P-0119", "P-0129", "P-0131",
}

HOSTED_DEMO_GNSS_DATASET_NAME = "[Synthetic / Illustrative] GNSS/CORS Survey Points - Ward 07"
HOSTED_DEMO_REQUIRED_STAGES = (
    "Ingestion", "CRS Normalization", "Schema Mapping", "Topology Validation",
    "Spatial Matching", "Conflict Detection", "Conflict Resolution",
    "Confidence Scoring", "Unified Land Record",
)


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


def _hosted_demo_state_is_ready(db):
    """Return true only when all bundled sources and generated outputs are present."""
    expected_names = [definition["name"] for definition in DATASET_DEFINITIONS]
    expected_names.append(HOSTED_DEMO_GNSS_DATASET_NAME)
    datasets = db.query(Dataset).filter(Dataset.name.in_(expected_names)).all()
    if len(datasets) != len(expected_names):
        return False
    if any(dataset.provenance != "synthetic_demo" or not dataset.feature_count
           or dataset.feature_count <= 0
           for dataset in datasets):
        return False

    dataset_ids = [dataset.id for dataset in datasets]
    actual_feature_counts = dict(
        db.query(Feature.dataset_id, func.count(Feature.id))
        .filter(Feature.dataset_id.in_(dataset_ids))
        .group_by(Feature.dataset_id)
        .all()
    )
    if any(actual_feature_counts.get(dataset.id, 0) != dataset.feature_count
           for dataset in datasets):
        return False

    # Confirm persisted outputs from the completed matching, topology,
    # attribute-mapping, confidence, and provenance stages.
    if db.query(MatchRecord.id).filter(MatchRecord.dataset_id.in_(dataset_ids)).first() is None:
        return False
    if db.query(AttributeMapping.id).filter(AttributeMapping.dataset_id.in_(dataset_ids)).first() is None:
        return False
    if db.query(ValidationResult.id).filter(ValidationResult.dataset_id.in_(dataset_ids)).first() is None:
        return False
    unified_records = db.query(UnifiedParcel).all()
    if not unified_records:
        return False
    ready_job_found = False
    for job in db.query(HarmonizationJob).filter(HarmonizationJob.status == "completed").order_by(HarmonizationJob.started_at.desc()).all():
        stages = {stage.get("name"): stage.get("status") for stage in (job.stages or [])
                  if isinstance(stage, dict)}
        if (job.total_processed == len(unified_records)
                and all(stages.get(stage) == "completed" for stage in HOSTED_DEMO_REQUIRED_STAGES)
                and stages.get("Change Detection") == "disabled"):
            ready_job_found = True
            break
    if not ready_job_found:
        return False
    if not any(
        record.confidence_score and isinstance(record.lineage, dict)
        and any(isinstance(source, dict) and source.get("dataset_id") in dataset_ids
                for source in record.lineage.values())
        for record in unified_records
    ):
        return False
    return True


def seed(reset=False):
    logger.info("Seed requested (free_demo_mode=%s, reset=%s, fixture_dir=%s)",
                settings.FREE_DEMO_MODE, reset, SAMPLE_DIR)
    if reset:
        print("Reset requested: dropping and recreating all tables...")
        Base.metadata.drop_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        # Serialize startup across Render instances. The hosted snapshot is
        # imported in this transaction, so the transaction-level advisory
        # lock is held until the snapshot commits or rolls back.
        if settings.FREE_DEMO_MODE and db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(26013, 2026)"))
        if not reset and settings.FREE_DEMO_MODE and _hosted_demo_state_is_ready(db):
            logger.info("Hosted demo prepared state verified; startup seed skipped")
            return False
        if settings.FREE_DEMO_MODE:
            from app.services.hosted_demo_snapshot import load_snapshot_transactionally
            counts = load_snapshot_transactionally(db, _hosted_demo_state_is_ready)
            logger.info("Hosted demo snapshot loaded transactionally; record_counts=%s", counts)
            return True
        if not reset and not settings.FREE_DEMO_MODE and db.query(Dataset).count():
            logger.info("Sample seed skipped: datasets already exist; existing database was left unchanged")
            return False
        if not os.path.isdir(SAMPLE_DIR):
            raise RuntimeError(f"Sample data directory not found: {SAMPLE_DIR}")
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
            print(f"  Ingested {ds.name}: {ds.feature_count} features (quality {ds.quality_score}%)")

        # GNSS points come from CSV
        gnss_csv_path = os.path.join(SAMPLE_DIR, "gnss_survey_points.csv")
        gnss_name = HOSTED_DEMO_GNSS_DATASET_NAME
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
        if settings.FREE_DEMO_MODE and job.status != "completed":
            raise RuntimeError(f"Hosted demo seed harmonization did not complete (status={job.status})")
        if job.status == "completed" and not settings.FREE_DEMO_MODE:
            detect_changes(db, job.id)
        logger.info("Seed complete; harmonization status: %s", job.status)
        print(f"\nSeed complete; harmonization status: {job.status}.")
        print("To demo Change Detection: upload data/sample/drone_buildings_v2.geojson as a new")
        print("'municipal' dataset via Data Sources, then re-run harmonization.")
        return True
    except Exception:
        logger.exception("Sample data seed failed")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load synthetic BHUMI-X sample data")
    parser.add_argument("--reset", action="store_true", help="destructively clear all tables before seeding")
    seed(reset=parser.parse_args().reset)
