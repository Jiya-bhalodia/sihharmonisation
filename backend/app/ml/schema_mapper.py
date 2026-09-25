"""
Intelligent attribute / schema mapping service.

Maps arbitrary source field names (survey_no, plot_no, khasra_no,
property_id, ...) to a fixed set of canonical fields (parcel_id,
owner_name, area, land_use, survey_number, building_count, ...) using
fuzzy string similarity against a synonym dictionary plus a lightweight
datatype-compatibility bonus. This is a real, computed confidence score
-- not a static lookup table.
"""
from typing import Dict, List, Any, Optional
from difflib import SequenceMatcher
from app.config import get_settings

settings = get_settings()

# Canonical field -> list of known synonyms seen across Indian land-record
# departments (revenue, municipal, survey, cadastral).
CANONICAL_SYNONYMS: Dict[str, List[str]] = {
    "parcel_id": ["parcel_id", "survey_no", "survey_number", "plot_no", "plot_number",
                  "property_id", "khasra_no", "khasra_number", "gat_no", "parcel_no"],
    "owner_name": ["owner", "owner_name", "landholder", "property_owner", "holder_name",
                   "pattadar_name", "khatedar"],
    "area": ["area", "area_sq_m", "area_sqm", "plot_area", "land_area", "extent",
             "area_sq_ft", "parcel_area"],
    "land_use": ["land_use", "landuse", "usage_type", "zone_type", "property_type",
                 "classification", "land_type"],
    "survey_number": ["survey_number", "survey_no", "sy_no", "s_no", "khasra_no"],
    "building_count": ["building_count", "num_buildings", "structure_count", "bldg_count"],
    "ward": ["ward", "ward_no", "ward_number", "zone", "block"],
    "address": ["address", "location", "locality", "street_address"],
    "status": ["status", "record_status", "mutation_status"],
}

CANONICAL_FIELDS = list(CANONICAL_SYNONYMS.keys())


def _normalize(field: str) -> str:
    return field.strip().lower().replace(" ", "_").replace("-", "_")


def _string_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _best_synonym_score(source_field: str, canonical: str) -> float:
    norm_source = _normalize(source_field)
    best = 0.0
    for synonym in CANONICAL_SYNONYMS[canonical]:
        score = _string_similarity(norm_source, _normalize(synonym))
        # Exact match after normalization gets full confidence
        if norm_source == _normalize(synonym):
            return 1.0
        # Substring containment is a strong signal
        if norm_source in _normalize(synonym) or _normalize(synonym) in norm_source:
            score = max(score, 0.85)
        best = max(best, score)
    return best


def _datatype_bonus(sample_value: Any, canonical: str) -> float:
    """Small bonus/penalty if the sample value's inferred type matches the
    expected type of the canonical field."""
    numeric_fields = {"area", "building_count"}
    is_numeric_value = isinstance(sample_value, (int, float)) and not isinstance(sample_value, bool)
    try:
        if isinstance(sample_value, str):
            float(sample_value)
            is_numeric_value = True
    except (ValueError, TypeError):
        pass

    if canonical in numeric_fields:
        return 0.08 if is_numeric_value else -0.05
    else:
        return 0.03 if not is_numeric_value else -0.02


def map_fields(source_fields: List[str], sample_row: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    For each source field, find the best-matching canonical field and a
    computed confidence score. Returns a list of mapping dicts:
    {source_field, canonical_field, confidence, method}
    """
    sample_row = sample_row or {}
    mappings = []

    for source_field in source_fields:
        best_canonical = None
        best_score = 0.0
        for canonical in CANONICAL_FIELDS:
            score = _best_synonym_score(source_field, canonical)
            if source_field in sample_row:
                score += _datatype_bonus(sample_row.get(source_field), canonical)
            score = max(0.0, min(1.0, score))
            if score > best_score:
                best_score = score
                best_canonical = canonical

        if best_canonical is None or best_score < 0.25:
            # No confident canonical match found; keep field as-is (unmapped)
            mappings.append({
                "source_field": source_field,
                "canonical_field": source_field,
                "confidence": round(best_score * 100, 1),
                "method": "unmapped",
            })
        else:
            mappings.append({
                "source_field": source_field,
                "canonical_field": best_canonical,
                "confidence": round(best_score * 100, 1),
                "method": "fuzzy_synonym",
            })

    return mappings


def needs_manual_review(confidence_pct: float) -> bool:
    return (confidence_pct / 100.0) < settings.SCHEMA_MAPPING_THRESHOLD


def apply_mapping(row: Dict[str, Any], mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Rewrite a raw properties dict into canonical field names."""
    canonical_row = {}
    for m in mappings:
        src, canon = m["source_field"], m["canonical_field"]
        if src in row:
            canonical_row[canon] = row[src]
    return canonical_row