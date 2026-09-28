"""Build the versioned hosted-demo snapshot from a fresh real pipeline run.

Run from backend/: ``venv/bin/python scripts/build_hosted_demo_snapshot.py``.
The script creates a disposable SQLite database, ingests only the checked-in
hosted fixture subset through the normal ingestion services, runs the complete
harmonization pipeline without the hosted synchronous deadline, then exports
only the rows consumed by hosted APIs. No existing database is opened.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _record(model, instance) -> dict:
    output = {}
    for column in model.__table__.columns:
        key = column.name
        if model.__name__ == "Dataset" and key == "file_path":
            continue
        value = getattr(instance, key)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        output[key] = value
    return output


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    root = backend_root.parent
    with tempfile.TemporaryDirectory(prefix="bhumix-hosted-snapshot-") as work:
        workdir = Path(work)
        os.environ["DEMO_MODE"] = "true"
        os.environ["FREE_DEMO_MODE"] = "false"
        os.environ["LOAD_SAMPLE_DATA"] = "false"
        os.environ["SQLITE_PATH"] = str(workdir / "source.db")
        os.environ["CHANGE_SNAPSHOT_PATH"] = str(workdir / "change-snapshot.json")

        import sys
        sys.path.insert(0, str(backend_root))
        from app.database import Base, engine, SessionLocal
        from app.models.orm import (
            AttributeMapping, Conflict, Dataset, Feature, HarmonizationJob,
            MatchRecord, UnifiedParcel, ValidationResult,
        )
        from app.sample_data import get_sample_data_dir
        from app.services.dataset_service import ingest_csv_latlon, ingest_geojson_dict
        from app.services.harmonization_service import run_harmonization
        from run_seed import (
            DATASET_DEFINITIONS, HOSTED_DEMO_GNSS_DATASET_NAME,
            _hosted_demo_geojson, _hosted_demo_gnss_csv,
        )

        Base.metadata.create_all(bind=engine)
        fixture_dir = get_sample_data_dir()
        with SessionLocal() as db:
            for definition in DATASET_DEFINITIONS:
                with (fixture_dir / definition["file"]).open(encoding="utf-8") as handle:
                    fixture = _hosted_demo_geojson(json.load(handle), definition["source_type"])
                ingest_geojson_dict(
                    db, fixture, definition["name"], definition["department"],
                    definition["source_type"], provenance="synthetic_demo",
                )
            ingest_csv_latlon(
                db, _hosted_demo_gnss_csv((fixture_dir / "gnss_survey_points.csv").read_bytes()),
                HOSTED_DEMO_GNSS_DATASET_NAME, "Survey Department", "gnss",
                provenance="synthetic_demo",
            )
            job = run_harmonization(db)
            if job.status != "completed":
                raise RuntimeError(f"Fresh hosted-fixture harmonization failed: {job.status}")

            # Snapshot-based change detection is intentionally unavailable on
            # Render Free. The real full local workflow ran it successfully;
            # the hosted job metadata represents the hosted capability.
            stages = [dict(stage) for stage in job.stages]
            for stage in stages:
                if stage.get("name") == "Change Detection":
                    stage.update(
                        status="disabled", processed=0,
                        detail="Snapshot-based change detection is disabled because this hosted free demo has no durable local disk.",
                    )
            job.stages = stages
            db.flush()

            records = {
                "datasets": [_record(Dataset, row) for row in db.query(Dataset).all()],
                "features": [_record(Feature, row) for row in db.query(Feature).all()],
                "unified_parcels": [_record(UnifiedParcel, row) for row in db.query(UnifiedParcel).all()],
                "matches": [_record(MatchRecord, row) for row in db.query(MatchRecord).all()],
                "conflicts": [_record(Conflict, row) for row in db.query(Conflict).all()],
                "attribute_mappings": [_record(AttributeMapping, row) for row in db.query(AttributeMapping).all()],
                "validation_results": [_record(ValidationResult, row) for row in db.query(ValidationResult).all()],
                "harmonization_jobs": [_record(HarmonizationJob, job)],
            }
            counts = {name: len(rows) for name, rows in records.items()}
            if counts["datasets"] != 7 or not counts["features"] or not counts["matches"] \
                    or not counts["attribute_mappings"] or not counts["conflicts"] \
                    or not counts["validation_results"] or not counts["unified_parcels"]:
                raise RuntimeError(f"Pipeline output is incomplete; refusing export: {counts}")
            if any(row["provenance"] != "synthetic_demo" for row in records["datasets"]):
                raise RuntimeError("Refusing to export a dataset without synthetic_demo provenance")

            payload = {
                "format": "bhumix-hosted-demo-snapshot",
                "schema_version": 1,
                "application_version": "1.1.0",
                "target_crs": "EPSG:4326",
                "provenance": "synthetic_demo",
                "source_fixtures": sorted([item["file"] for item in DATASET_DEFINITIONS] + ["gnss_survey_points.csv"]),
                "record_counts": counts,
                "records": records,
            }
            artifact = {"payload": payload, "sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest()}
            output = backend_root / "hosted_demo_snapshot.v1.json"
            output.write_bytes(json.dumps(artifact, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")
            print(f"snapshot_path={output}")
            print(f"snapshot_bytes={output.stat().st_size}")
            print(f"completed_job_id={job.id}")
            print(f"record_counts={json.dumps(counts, sort_keys=True)}")
            print(f"confidence_records={sum(row['confidence_score'] is not None for row in records['unified_parcels'])}")
            print(f"lineage_records={sum(bool(row['lineage']) for row in records['unified_parcels'])}")
        engine.dispose()


if __name__ == "__main__":
    main()
