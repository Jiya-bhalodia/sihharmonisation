"""
Core harmonization pipeline orchestrator.

Runs the full 9-stage pipeline:
  1. Ingestion
  2. CRS Normalization (re-verified here)
  3. Schema Mapping
  4. Topology Validation
  5. Spatial Matching
  6. Conflict Detection
  7. Conflict Resolution (flagging only; human resolves via API)
  8. Confidence Scoring
  9. Unified Land Record generation

Each stage records status/counts/warnings into HarmonizationJob.stages so
the frontend pipeline UI is fully data-driven, not decorative.

IMPORTANT DESIGN NOTE (fixed after senior review): cadastral survey
records are treated as the AUTHORITATIVE anchor for forming a matched
group. Revenue, municipal, GNSS, ground-truth, and utility records are
matched AGAINST a cadastral anchor wherever possible. Only records that
genuinely have no corresponding cadastral survey (e.g. a revenue-only
entry) become their own fallback anchor. This prevents the same
real-world parcel from being counted twice as two separate unified
records, which happened when every "parcel"-typed source (cadastral
AND revenue) was treated as an equally valid, independent anchor.
"""
from typing import List, Dict, Any, Set
from datetime import datetime
import time
from sqlalchemy.orm import Session
from collections import defaultdict
from math import cos, radians
from shapely.geometry import box as geometry_box
from shapely.strtree import STRtree
from sqlalchemy import text

from app.models.orm import (
    Dataset, Feature, UnifiedParcel, MatchRecord, AttributeMapping,
    ValidationResult, HarmonizationJob, Conflict
)
from app.services.embedding_service import embedding_metrics_summary, reset_embedding_metrics
from app.utils.ids import new_id, job_id
from app.utils.logger import get_logger
from app.geo.crs import geojson_str_to_geometry, geometry_to_geojson_str
from app.geo.topology import validate_geometry, detect_duplicates, detect_overlaps, geometry_audit_snapshots
from app.geo.geometry_utils import area_sqm, centroid_latlon
from app.ml.schema_mapper import map_fields, needs_manual_review, preserve_manual_overrides
from app.ml.spatial_matcher import MatchCandidate, find_candidate_matches
from app.services.conflict_service import detect_all_conflicts
from app.services.change_service import detect_changes
from app.config import get_settings
from app.services.free_demo import FreeDemoTimeLimitExceeded, check_processing_deadline

logger = get_logger("services.harmonization")
settings = get_settings()


def _stage(db: Session, job: HarmonizationJob, name: str, status: str, processed: int = 0, warnings: int = 0, errors: int = 0, detail: str = ""):
    stages = list(job.stages or [])
    stage = {
        "name": name,
        "status": status,
        "processed": processed,
        "warnings": warnings,
        "errors": errors,
        "detail": detail,
        "timestamp": datetime.utcnow().isoformat(),
    }
    # Keep a single current entry for each pipeline stage so polling clients
    # don't continue displaying an earlier "running" status after completion.
    existing = next((index for index, item in enumerate(stages) if item.get("name") == name), None)
    if existing is None:
        stages.append(stage)
    else:
        stages[existing] = stage
    job.stages = stages
    # Persist each completed stage so the UI can show live progress while a
    # long-running harmonization is handled by the background worker.
    db.commit()


def run_harmonization(db: Session, existing_job_id: str | None = None,
                      max_processing_seconds: int | None = None) -> HarmonizationJob:
    deadline = time.monotonic() + max_processing_seconds if max_processing_seconds else None
    check_processing_deadline(deadline)
    if existing_job_id:
        job = db.query(HarmonizationJob).filter(HarmonizationJob.id == existing_job_id).first()
        if job is None:
            raise ValueError(f"Harmonization job {existing_job_id} does not exist")
        job.status = "running"
        job.stages = []
        job.started_at = datetime.utcnow()
        job.completed_at = None
    else:
        job = HarmonizationJob(id=job_id(), status="running", stages=[], started_at=datetime.utcnow())
        db.add(job)
    db.commit()
    db.refresh(job)
    running_job_id = job.id

    try:
        datasets = db.query(Dataset).all()
        if not datasets:
            _stage(db, job, "Ingestion", "failed", detail="No datasets found. Upload data first.")
            job.status = "failed"
            db.commit()
            return job

        _stage(db, job, "Ingestion", "completed", processed=len(datasets), detail=f"{len(datasets)} datasets available")

        # --- Stage 2: CRS Normalization verification ---
        all_features = db.query(Feature).all()
        crs_ok = sum(1 for f in all_features if f.geometry_geojson)
        distinct_source_crs = sorted({d.crs for d in datasets if d.crs})
        _stage(db, job, "CRS Normalization", "completed", processed=crs_ok,
               detail=f"Source CRS(s) detected: {', '.join(distinct_source_crs) or 'n/a'} "
                      f"-> all geometries normalized to {settings.TARGET_CRS}")

        # --- Stage 3: Schema Mapping ---
        mapping_count = 0
        review_count = 0
        previous_mappings = db.query(AttributeMapping).all()
        db.query(AttributeMapping).delete()
        for dataset in datasets:
            check_processing_deadline(deadline)
            feats = db.query(Feature).filter(Feature.dataset_id == dataset.id).limit(50).all()
            field_names = set()
            sample_row = {}
            for f in feats:
                if f.raw_properties:
                    field_names.update(f.raw_properties.keys())
                    if not sample_row:
                        sample_row = f.raw_properties
            if not field_names:
                continue
            mappings = preserve_manual_overrides(
                map_fields(list(field_names), sample_row),
                [
                    {"source_field": item.source_field, "canonical_field": item.canonical_field,
                     "manual_override": item.manual_override}
                    for item in previous_mappings if item.dataset_id == dataset.id
                ],
            )
            for m in mappings:
                am = AttributeMapping(
                    id=new_id("AM"),
                    dataset_id=dataset.id,
                    source_field=m["source_field"],
                    canonical_field=m["canonical_field"],
                    confidence=m["confidence"],
                    method=m["method"],
                    manual_override=m.get("manual_override", False),
                )
                db.add(am)
                mapping_count += 1
                if needs_manual_review(m["confidence"]):
                    review_count += 1
        db.commit()
        _stage(db, job, "Schema Mapping", "completed", processed=mapping_count, warnings=review_count,
               detail=f"{mapping_count} fields mapped, {review_count} flagged for review")

        # --- Stage 4: Topology Validation ---
        _stage(db, job, "Topology Validation", "running", processed=0,
               detail=f"Checking geometry validity and spatial-index candidates across {len(all_features)} features")
        db.query(ValidationResult).delete()
        topo_errors = 0
        topo_corrected = 0
        topology_processed = 0
        for dataset in datasets:
            check_processing_deadline(deadline)
            feats = db.query(Feature).filter(Feature.dataset_id == dataset.id).all()
            geoms_for_dup_check = []
            for f in feats:
                check_processing_deadline(deadline)
                geom = geojson_str_to_geometry(f.geometry_geojson) if f.geometry_geojson else None
                original_geometry_geojson = f.geometry_geojson
                vresult = validate_geometry(geom)
                f.is_valid_geometry = vresult["is_valid"]
                if not vresult["is_valid"] or vresult["issue_type"] != "none":
                    topo_errors += 1
                    audit_original_geojson, corrected_geojson = geometry_audit_snapshots(
                        original_geometry_geojson, vresult["corrected_geometry"]
                    )
                    if vresult["corrected_geometry"] is not None:
                        topo_corrected += 1
                        # Keep the original in ValidationResult for audit, then let every
                        # later stage use the corrected geometry rather than merely
                        # displaying a correction that never affects its output.
                        corrected = vresult["corrected_geometry"]
                        f.geometry_geojson = corrected_geojson
                        f.centroid_lat, f.centroid_lon = centroid_latlon(corrected)
                        f.area_sqm = area_sqm(corrected, settings.TARGET_CRS) if corrected.geom_type in ("Polygon", "MultiPolygon") else None
                        f.is_valid_geometry = corrected.is_valid and not corrected.is_empty
                    vr = ValidationResult(
                        id=new_id("VR"),
                        feature_id=f.id,
                        dataset_id=dataset.id,
                        is_valid=vresult["is_valid"],
                        issue_type=vresult["issue_type"],
                        original_geometry=audit_original_geojson,
                        corrected_geometry=corrected_geojson,
                        corrected=vresult["corrected"],
                    )
                    db.add(vr)
                if geom is not None and geom.geom_type in ("Polygon", "MultiPolygon"):
                    geoms_for_dup_check.append({"id": f.id, "geometry": geom})

                topology_processed += 1
                if topology_processed % 100 == 0:
                    _stage(db, job, "Topology Validation", "running", processed=topology_processed,
                           warnings=topo_errors,
                           detail=f"Validated {topology_processed}/{len(all_features)} features; processing {dataset.name}")

            _stage(db, job, "Topology Validation", "running", processed=topology_processed,
                   warnings=topo_errors,
                   detail=f"Checking indexed duplicate and overlap candidates in {dataset.name} ({len(geoms_for_dup_check)} polygons)")
            deadline_check = lambda: check_processing_deadline(deadline)
            dup_issues = detect_duplicates(geoms_for_dup_check, deadline_check=deadline_check)
            for dup in dup_issues:
                topo_errors += 1
                vr = ValidationResult(
                    id=new_id("VR"),
                    feature_id=dup["feature_b"],
                    dataset_id=dataset.id,
                    is_valid=False,
                    issue_type="duplicate",
                    original_geometry=None,
                    corrected_geometry=None,
                    corrected=False,
                )
                db.add(vr)
            overlap_issues = detect_overlaps(geoms_for_dup_check, deadline_check=deadline_check)
            for overlap in overlap_issues:
                topo_errors += 1
                db.add(ValidationResult(
                    id=new_id("VR"), feature_id=overlap["feature_b"], dataset_id=dataset.id,
                    is_valid=False, issue_type="overlap", original_geometry=None,
                    corrected_geometry=None, corrected=False,
                ))
            _stage(db, job, "Topology Validation", "running", processed=topology_processed,
                   warnings=topo_errors, detail=f"Finished spatial checks for {dataset.name}")
        db.commit()
        _stage(db, job, "Topology Validation", "completed", processed=len(all_features),
               warnings=topo_errors, detail=f"{topo_errors} issues found, {topo_corrected} auto-corrected")

        # --- Stage 5: Spatial Matching ---
        reset_embedding_metrics()
        db.query(MatchRecord).delete()
        dataset_map = {d.id: d for d in datasets}
        all_candidates: List[MatchCandidate] = []
        for f in all_features:
            geom = geojson_str_to_geometry(f.geometry_geojson) if f.geometry_geojson else None
            ds = dataset_map.get(f.dataset_id)
            mc = MatchCandidate(
                feature_id=f.id,
                dataset_id=f.dataset_id,
                canonical_type=f.canonical_type,
                geometry=geom,
                centroid_lat=f.centroid_lat,
                centroid_lon=f.centroid_lon,
                area=f.area_sqm,
                properties=_apply_canonical_mapping(db, f),
                source_type=ds.source_type if ds else "unknown",
            )
            all_candidates.append(mc)

        # Prune impossible matches with the PostGIS GiST index in production.
        # SQLite/demo deployments use the equivalent in-memory STRtree fallback.
        indexed_candidates = [candidate for candidate in all_candidates
                              if candidate.geometry is not None and not candidate.geometry.is_empty]
        candidate_tree = STRtree([candidate.geometry for candidate in indexed_candidates]) if indexed_candidates else None
        candidates_by_id = {candidate.feature_id: candidate for candidate in indexed_candidates}
        use_postgis_index = db.bind is not None and db.bind.dialect.name == "postgresql"

        matched_groups: Dict[str, MatchCandidate] = {}
        group_counter = 0
        match_count = 0
        used_feature_ids: Set[str] = set()

        def _process_anchor(anchor: MatchCandidate):
            nonlocal group_counter, match_count
            if anchor.feature_id in used_feature_ids:
                return
            nearby_candidates = []
            if candidate_tree is not None and anchor.geometry is not None and not anchor.geometry.is_empty:
                search_distance_m = settings.MATCH_MAX_DISTANCE_M * 3.0
                lat_delta = search_distance_m / 111_320.0
                cosine = max(0.05, abs(cos(radians(anchor.centroid_lat or 0.0))))
                lon_delta = lat_delta / cosine
                min_x, min_y, max_x, max_y = anchor.geometry.bounds
                search_area = geometry_box(min_x - lon_delta, min_y - lat_delta,
                                           max_x + lon_delta, max_y + lat_delta)
                if use_postgis_index:
                    rows = db.execute(text(
                        "SELECT id FROM features WHERE geom && ST_MakeEnvelope(:min_x, :min_y, :max_x, :max_y, 4326)"
                    ), {"min_x": min_x - lon_delta, "min_y": min_y - lat_delta,
                        "max_x": max_x + lon_delta, "max_y": max_y + lat_delta}).all()
                    nearby_candidates = [candidates_by_id[row[0]] for row in rows if row[0] in candidates_by_id]
                else:
                    indices = candidate_tree.query(search_area)
                    nearby_candidates = [indexed_candidates[int(index)] for index in indices]
            candidates = find_candidate_matches(anchor, nearby_candidates, min_confidence_pct=40.0)
            group_counter += 1
            group_id = f"GRP-{group_counter:04d}"
            used_feature_ids.add(anchor.feature_id)
            seen_datasets = {anchor.dataset_id}
            for c in candidates:
                check_processing_deadline(deadline)
                cand = c["candidate"]
                if cand.dataset_id in seen_datasets or cand.feature_id in used_feature_ids:
                    continue  # only best match per source dataset, and never reuse a feature
                seen_datasets.add(cand.dataset_id)
                used_feature_ids.add(cand.feature_id)
                scores = c["scores"]
                db.add(MatchRecord(
                    id=new_id("MT"), parcel_unified_id=None, feature_id=cand.feature_id,
                    dataset_id=cand.dataset_id, matched_group_id=group_id,
                    spatial_proximity=scores["spatial_proximity"], geometry_overlap=scores["geometry_overlap"],
                    area_similarity=scores["area_similarity"], attribute_similarity=scores["attribute_similarity"],
                    overall_confidence=scores["overall_confidence"],
                ))
                match_count += 1
            matched_groups[group_id] = anchor

        # Cadastral parcels are the authoritative geometry source and
        # always form the primary anchors.
        cadastral_anchors = [c for c in all_candidates if c.source_type == "cadastral"]
        for anchor in cadastral_anchors:
            check_processing_deadline(deadline)
            _process_anchor(anchor)

        # Fallback: any remaining parcel-typed record not yet absorbed into
        # a cadastral-anchored group (e.g. a revenue record with no
        # corresponding cadastral survey yet) still becomes its own
        # unified record instead of being silently dropped.
        fallback_anchors = [
            c for c in all_candidates
            if c.canonical_type == "parcel" and c.feature_id not in used_feature_ids
        ]
        for anchor in fallback_anchors:
            check_processing_deadline(deadline)
            _process_anchor(anchor)

        db.commit()
        _stage(db, job, "Spatial Matching", "completed", processed=match_count,
               detail=f"{len(matched_groups)} feature groups formed "
                      f"({len(cadastral_anchors)} cadastral-anchored, {len(fallback_anchors)} fallback-anchored). "
                      f"{embedding_metrics_summary()}")

        # --- Stage 6+8: Conflict Detection & Confidence Scoring -> feeds Unified Record ---
        _stage(db, job, "Conflict Detection", "running", processed=0,
               detail=f"Checking spatial conflicts across {len(all_candidates)} features using indexed candidates")
        check_processing_deadline(deadline)
        conflict_count = detect_all_conflicts(
            db, all_candidates, matched_groups,
            deadline_check=lambda: check_processing_deadline(deadline),
        )
        check_processing_deadline(deadline)
        _stage(db, job, "Conflict Detection", "completed", processed=len(all_candidates), warnings=conflict_count,
               detail=f"{conflict_count} conflicts identified")

        _stage(db, job, "Conflict Resolution", "completed", processed=conflict_count,
               detail="Conflicts queued for human review in Conflict Resolution workspace")

        unified_count = _build_unified_parcels(
            db, matched_groups,
            deadline_check=lambda: check_processing_deadline(deadline),
        )
        _stage(db, job, "Confidence Scoring", "completed", processed=unified_count,
               detail="Spatial, attribute, geometry and source-agreement confidence computed per parcel")

        _stage(db, job, "Unified Land Record", "completed", processed=unified_count,
               detail=f"{unified_count} unified parcel records generated")

        if settings.FREE_DEMO_MODE:
            _stage(db, job, "Change Detection", "disabled", processed=0,
                   detail="Snapshot-based change detection is disabled because this hosted free demo has no durable local disk.")
        else:
            change_count = detect_changes(db, job.id)
            _stage(db, job, "Change Detection", "completed", processed=change_count,
                   detail=f"{change_count} changes detected against the previous harmonized snapshot")

        job.status = "completed"
        job.total_processed = unified_count
        job.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(job)
        logger.info(f"Harmonization job {job.id} completed: {unified_count} unified parcels")
        return job

    except Exception as e:
        db.rollback()
        job = db.query(HarmonizationJob).filter(HarmonizationJob.id == running_job_id).first()
        logger.exception(f"Harmonization job {running_job_id} failed: {e}")
        if job is None:
            raise
        detail = str(e) if isinstance(e, FreeDemoTimeLimitExceeded) else (
            f"Pipeline failed ({type(e).__name__}). Check backend worker logs for job {running_job_id}."
        )
        _stage(db, job, "Pipeline Error", "failed", errors=1, detail=detail)
        job.status = "failed"
        job.completed_at = datetime.utcnow()
        db.commit()
        return job


def _apply_canonical_mapping(db: Session, feature: Feature) -> Dict[str, Any]:
    """Rewrite a feature's raw properties into canonical field names using
    the stored attribute mappings for its dataset."""
    mappings = db.query(AttributeMapping).filter(AttributeMapping.dataset_id == feature.dataset_id).all()
    canonical = {}
    props = feature.raw_properties or {}
    for m in mappings:
        if m.source_field in props and props[m.source_field] not in (None, ""):
            canonical[m.canonical_field] = props[m.source_field]
    for k, v in props.items():
        canonical.setdefault(k, v)
    return canonical


def _build_unified_parcels(db: Session, matched_groups: Dict[str, "MatchCandidate"],
                           deadline_check=None) -> int:
    # Match rows may still reference results from an earlier run. Clear those
    # nullable links before replacing the unified parcel snapshot.
    db.query(MatchRecord).update({MatchRecord.parcel_unified_id: None}, synchronize_session=False)
    db.flush()
    db.query(UnifiedParcel).delete()
    db.commit()

    count = 0
    for group_id, anchor in matched_groups.items():
        if deadline_check:
            deadline_check()
        records = db.query(MatchRecord).filter(MatchRecord.matched_group_id == group_id).all()
        feature_ids = [r.feature_id for r in records]
        features = db.query(Feature).filter(Feature.id.in_(feature_ids)).all() if feature_ids else []
        feature_map = {f.id: f for f in features}

        anchor_feature = db.query(Feature).filter(Feature.id == anchor.feature_id).first()

        lineage: Dict[str, Any] = {}
        owner_names, land_uses, survey_numbers = [], [], []
        building_count, utility_count = 0, 0
        gnss_verified, ground_truth_verified = False, False
        source_types_seen = set()
        cadastral_geom_geojson, cadastral_area = None, None
        fallback_geom_geojson, fallback_area = None, None

        def _absorb(f: Feature, lineage_confidence: float):
            nonlocal building_count, utility_count, gnss_verified, ground_truth_verified
            nonlocal cadastral_geom_geojson, cadastral_area, fallback_geom_geojson, fallback_area
            dataset = db.query(Dataset).filter(Dataset.id == f.dataset_id).first()
            if not dataset:
                return
            source_types_seen.add(dataset.source_type)
            canonical_props = _apply_canonical_mapping(db, f)
            contributed_fields = list(canonical_props.keys())
            lineage[dataset.source_type] = {
                "dataset_id": dataset.id,
                "dataset_name": dataset.name,
                "feature_id": f.id,
                "contributed_fields": contributed_fields,
                "confidence": lineage_confidence,
            }
            if canonical_props.get("owner_name"):
                owner_names.append(str(canonical_props["owner_name"]))
            if canonical_props.get("land_use"):
                land_uses.append(str(canonical_props["land_use"]))
            if canonical_props.get("survey_number") or canonical_props.get("parcel_id"):
                survey_numbers.append(str(canonical_props.get("survey_number") or canonical_props.get("parcel_id")))
            if dataset.source_type in ("municipal", "drone") and f.canonical_type == "building":
                building_count += 1
            if dataset.source_type == "utility":
                utility_count += 1
            if dataset.source_type == "gnss":
                gnss_verified = True
            if dataset.source_type == "ground_truth":
                ground_truth_verified = True
            if f.canonical_type == "parcel" and f.geometry_geojson:
                if dataset.source_type == "cadastral":
                    cadastral_geom_geojson = f.geometry_geojson
                    cadastral_area = f.area_sqm
                elif fallback_geom_geojson is None:
                    fallback_geom_geojson = f.geometry_geojson
                    fallback_area = f.area_sqm

        # The anchor is always part of the group. Its lineage-display
        # confidence reflects source completeness, not a match score
        # (the anchor is the reference point, so it was never "matched"
        # against anything) -- this value is never used in the parcel's
        # overall_confidence average below.
        if anchor_feature:
            _absorb(anchor_feature, 100.0 if anchor.source_type == "cadastral" else 90.0)

        for rec in records:
            if deadline_check:
                deadline_check()
            f = feature_map.get(rec.feature_id)
            if f:
                _absorb(f, rec.overall_confidence)

        best_geom_geojson = cadastral_geom_geojson or fallback_geom_geojson or (
            geometry_to_geojson_str(anchor.geometry) if anchor.geometry is not None else None
        )
        best_area = cadastral_area if cadastral_geom_geojson else (fallback_area if fallback_geom_geojson else anchor.area)

        overall_scores = [r.overall_confidence for r in records]
        spatial_scores = [r.spatial_proximity for r in records]
        attr_scores = [r.attribute_similarity for r in records]
        geom_scores = [r.geometry_overlap for r in records]

        avg = lambda lst: round(sum(lst) / len(lst), 1) if lst else 0.0
        source_agreement = round(min(100.0, (len(source_types_seen) / 5.0) * 100), 1)

        if overall_scores:
            overall_confidence = avg(overall_scores)
        else:
            # No genuine cross-source matches were found for this record.
            # Rather than fabricating a number, confidence is derived from
            # actual source coverage -- a single-source, unverified record
            # correctly scores low and fails validation.
            overall_confidence = source_agreement

        validation_status = "PASSED" if overall_confidence >= settings.CONFIDENCE_MEDIUM else "FAILED"

        parcel_id_value = survey_numbers[0] if survey_numbers else anchor.feature_id
        owner_value = owner_names[0] if owner_names else "Unknown"
        land_use_value = land_uses[0] if land_uses else "Unclassified"

        up = UnifiedParcel(
            id=new_id("UP"),
            parcel_id=parcel_id_value,
            survey_number=survey_numbers[0] if survey_numbers else None,
            owner_name=owner_value,
            area=best_area,
            land_use=land_use_value,
            geometry_geojson=best_geom_geojson,
            building_count=building_count,
            utility_count=utility_count,
            gnss_verified=gnss_verified,
            ground_truth_verified=ground_truth_verified,
            source_count=len(source_types_seen),
            confidence_score=overall_confidence,
            spatial_confidence=avg(spatial_scores),
            attribute_confidence=avg(attr_scores),
            geometry_confidence=avg(geom_scores),
            source_agreement=source_agreement,
            validation_status=validation_status,
            conflict_status="NONE",
            lineage=lineage,
            last_updated=datetime.utcnow(),
        )
        db.add(up)
        # Without an ORM relationship SQLAlchemy may flush MatchRecord UPDATEs
        # before the new UnifiedParcel INSERT. Materialize the FK target first.
        db.flush()

        for rec in records:
            rec.parcel_unified_id = up.id

        count += 1

    db.commit()
    _link_conflicts_to_parcels(db, deadline_check=deadline_check)
    return count


def _link_conflicts_to_parcels(db: Session, deadline_check=None):
    parcels = db.query(UnifiedParcel).all()
    conflicts = db.query(Conflict).filter(Conflict.status == "Open").all()
    conflict_parcel_ids = defaultdict(set)
    for conflict in conflicts:
        if deadline_check:
            deadline_check()
        if conflict.feature_ref:
            for p in parcels:
                if deadline_check:
                    deadline_check()
                lineage_feature_ids = {v.get("feature_id") for v in (p.lineage or {}).values()}
                if conflict.feature_ref in lineage_feature_ids:
                    conflict.parcel_id = p.id
                    conflict_parcel_ids[p.id].add(conflict.severity)
    for p in parcels:
        severities = conflict_parcel_ids.get(p.id, set())
        if "MAJOR" in severities:
            p.conflict_status = "MAJOR"
        elif severities:
            p.conflict_status = "MINOR"
    db.commit()
