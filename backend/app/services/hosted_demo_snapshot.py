"""Validated, transactional loader for the immutable hosted demo snapshot."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.orm import (
    AttributeMapping, ChangeEvent, Conflict, Dataset, Feature, HarmonizationJob,
    MatchRecord, UnifiedParcel, ValidationResult,
)

SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "hosted_demo_snapshot.v1.json"
SNAPSHOT_FORMAT = "bhumix-hosted-demo-snapshot"
SNAPSHOT_VERSION = 1

TABLES = {
    "datasets": Dataset,
    "features": Feature,
    "unified_parcels": UnifiedParcel,
    "matches": MatchRecord,
    "conflicts": Conflict,
    "attribute_mappings": AttributeMapping,
    "validation_results": ValidationResult,
    "harmonization_jobs": HarmonizationJob,
}
REPLACEABLE_RESULT_TABLES = (MatchRecord, Conflict, ValidationResult, AttributeMapping, UnifiedParcel, ChangeEvent)
ORPHAN_CHECK_TABLES = (*REPLACEABLE_RESULT_TABLES, HarmonizationJob, ChangeEvent)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _parse_snapshot(path: Path = SNAPSHOT_PATH) -> dict:
    if not path.is_file():
        raise RuntimeError(f"Hosted demo snapshot is missing: {path.name}")
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        payload = artifact["payload"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError(f"Hosted demo snapshot is unreadable or malformed: {path.name}") from error
    digest = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    if artifact.get("sha256") != digest:
        raise RuntimeError("Hosted demo snapshot checksum mismatch")
    if payload.get("format") != SNAPSHOT_FORMAT or payload.get("schema_version") != SNAPSHOT_VERSION:
        raise RuntimeError("Hosted demo snapshot format/version is incompatible")
    if payload.get("application_version") != "1.1.0" or payload.get("target_crs") != "EPSG:4326":
        raise RuntimeError("Hosted demo snapshot application/CRS contract is incompatible")
    if payload.get("provenance") != "synthetic_demo":
        raise RuntimeError("Hosted demo snapshot provenance is not synthetic_demo")
    records = payload.get("records")
    counts = payload.get("record_counts")
    if not isinstance(records, dict) or not isinstance(counts, dict):
        raise RuntimeError("Hosted demo snapshot is missing records/count metadata")
    if set(records) != set(TABLES) or any(not isinstance(records[key], list) for key in TABLES):
        raise RuntimeError("Hosted demo snapshot record table contract is incompatible")
    if any(counts.get(key) != len(records[key]) for key in TABLES):
        raise RuntimeError("Hosted demo snapshot record counts do not match its payload")
    if len(records["datasets"]) != 7 or not all(rows for name, rows in records.items() if name != "harmonization_jobs"):
        raise RuntimeError("Hosted demo snapshot is incomplete")
    if len(records["harmonization_jobs"]) != 1:
        raise RuntimeError("Hosted demo snapshot must contain exactly one completed harmonization job")
    if any(row.get("provenance") != "synthetic_demo" for row in records["datasets"]):
        raise RuntimeError("Hosted demo snapshot contains non-synthetic dataset provenance")
    for table_name, model in TABLES.items():
        allowed = {column.name for column in model.__table__.columns}
        for row in records[table_name]:
            if not isinstance(row, dict) or not set(row).issubset(allowed):
                raise RuntimeError(f"Hosted demo snapshot has incompatible fields in {table_name}")
    # Reject any local path or credential-like column accidentally included.
    forbidden = {"file_path", "password", "password_hash", "secret", "token", "local_path", "ip_address"}
    for table_rows in records.values():
        if any(forbidden.intersection(row) for row in table_rows):
            raise RuntimeError("Hosted demo snapshot contains a forbidden field")
    if any(not isinstance(row.get("geometry_geojson"), (str, type(None))) for name in ("features", "unified_parcels") for row in records[name]):
        raise RuntimeError("Hosted demo snapshot geometry is not GeoJSON text")
    for name in ("features", "unified_parcels"):
        for row in records[name]:
            geometry = row.get("geometry_geojson")
            if geometry is not None:
                try:
                    json.loads(geometry)
                except (TypeError, json.JSONDecodeError) as error:
                    raise RuntimeError(f"Hosted demo snapshot has invalid GeoJSON in {name}") from error
    job = records["harmonization_jobs"][0]
    if job.get("status") != "completed":
        raise RuntimeError("Hosted demo snapshot job is not completed")
    return payload


def _parse_dates(model, row: dict) -> dict:
    output = dict(row)
    for column in model.__table__.columns:
        if column.name not in output or output[column.name] is None:
            continue
        value = output[column.name]
        if column.type.python_type is datetime and isinstance(value, str):
            output[column.name] = datetime.fromisoformat(value)
    return output


def _has_any_rows(db: Session, model) -> bool:
    return db.query(model).limit(1).first() is not None


def _clear_partial_synthetic_state(db: Session, expected_names: set[str]) -> None:
    """Replace only an incomplete synthetic-only seed; reject mixed user data."""
    datasets = db.query(Dataset).all()
    if datasets:
        if any(dataset.name not in expected_names or dataset.provenance != "synthetic_demo" for dataset in datasets):
            raise RuntimeError("Hosted demo snapshot will not overwrite unrelated or non-synthetic datasets")
        dataset_ids = {dataset.id for dataset in datasets}
        feature_ids = {row[0] for row in db.query(Feature.id).all()}
        unified_ids = {row[0] for row in db.query(UnifiedParcel.id).all()}
        for record in db.query(MatchRecord).all():
            if (record.dataset_id not in dataset_ids or record.feature_id not in feature_ids
                    or (record.parcel_unified_id and record.parcel_unified_id not in unified_ids)):
                raise RuntimeError("Hosted demo snapshot will not replace match results linked to unrelated data")
        for model in (AttributeMapping, ValidationResult):
            for record in db.query(model).all():
                if record.dataset_id not in dataset_ids:
                    raise RuntimeError("Hosted demo snapshot will not replace derived records linked to unrelated data")
                if isinstance(record, ValidationResult) and record.feature_id not in feature_ids:
                    raise RuntimeError("Hosted demo snapshot will not replace topology results linked to unrelated data")
        for conflict in db.query(Conflict).all():
            if ((conflict.feature_ref and conflict.feature_ref not in feature_ids)
                    or (conflict.source_a and conflict.source_a not in dataset_ids)
                    or (conflict.source_b and conflict.source_b not in dataset_ids)):
                raise RuntimeError("Hosted demo snapshot will not replace conflicts linked to unrelated data")
        for parcel in db.query(UnifiedParcel).all():
            for source in (parcel.lineage or {}).values():
                if (not isinstance(source, dict) or source.get("dataset_id") not in dataset_ids
                        or source.get("feature_id") not in feature_ids):
                    raise RuntimeError("Hosted demo snapshot will not replace unified records with unrelated lineage")
        if any(event.feature_ref not in feature_ids for event in db.query(ChangeEvent).all()):
            raise RuntimeError("Hosted demo snapshot will not replace change events linked to unrelated data")
        # Existing derived tables are pipeline outputs across the current
        # dataset collection. Since every dataset is a known synthetic demo
        # source, replacing these rows is scoped to that demo state.
        for model in REPLACEABLE_RESULT_TABLES:
            db.query(model).delete(synchronize_session=False)
        db.query(Feature).delete(synchronize_session=False)
        db.query(Dataset).delete(synchronize_session=False)
        return
    if any(_has_any_rows(db, model) for model in (*ORPHAN_CHECK_TABLES, Feature)):
        raise RuntimeError("Hosted demo snapshot found orphaned application data and will not overwrite it")


def load_snapshot_transactionally(db: Session, ready_check, path: Path = SNAPSHOT_PATH) -> dict:
    """Load validated state atomically; caller holds the PG advisory lock."""
    payload = _parse_snapshot(path)
    records = payload["records"]
    expected_names = {row["name"] for row in records["datasets"]}
    try:
        # run_seed acquired a transaction-level PostgreSQL advisory lock
        # before its readiness query. Keep that transaction open through the
        # import so another Render instance cannot enter between checking and
        # committing the snapshot.
        _clear_partial_synthetic_state(db, expected_names)
        for key in ("datasets", "features", "unified_parcels", "matches", "conflicts", "attribute_mappings", "validation_results", "harmonization_jobs"):
            model = TABLES[key]
            db.bulk_insert_mappings(model, [_parse_dates(model, row) for row in records[key]])
        db.flush()
        if not ready_check(db):
            raise RuntimeError("Loaded hosted snapshot failed persisted-state readiness checks")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return payload["record_counts"]
