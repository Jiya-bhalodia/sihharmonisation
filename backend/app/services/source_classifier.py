"""Rules-first dataset type suggestion with an optional localhost-only LLM tie-breaker."""
import json
import re
from urllib.request import Request, urlopen

from app.config import get_settings

SOURCE_TYPES = {
    "cadastral", "revenue", "municipal", "gnss", "ground_truth", "utility",
    "drone", "orthoimagery", "dsm", "dtm",
}

RULES = {
    "cadastral": ("cadastral", "parcel boundary", "survey map", "gat map", "cts map"),
    "revenue": ("revenue", "7/12", "712", "khata", "land record", "ownership"),
    "municipal": ("municipal", "building footprint", "property tax", "municipality"),
    "gnss": ("gnss", "cors", "gps survey", "survey point"),
    "ground_truth": ("ground truth", "ground_truth", "field verification", "field survey"),
    "utility": ("utility", "sewer", "water pipeline", "electric network", "drainage"),
    "drone": ("drone", "uav", "aerial image", "orthomosaic"),
    "orthoimagery": ("orthoimagery", "ortho imagery", "ori", "orthophoto"),
    "dsm": ("dsm", "surface model", "digital surface"),
    "dtm": ("dtm", "terrain model", "digital terrain"),
}

FIELD_CUES = {
    "cadastral": {"parcel_id", "survey_number", "survey_no", "gat_no", "cts_no", "khasra_no"},
    "revenue": {"owner_name", "khata_number", "landholder", "pattadar_name", "survey_gat_no"},
    "municipal": {"building_id", "property_tax_id", "building_use", "floor_count"},
    "gnss": {"horizontal_accuracy", "horizontal_accuracy_m", "gnss_id", "fix_quality"},
    "ground_truth": {"verified", "verification_date", "field_observation", "ground_truth"},
    "utility": {"pipe_diameter", "asset_type", "network_type", "utility_id"},
}


def _local_llm_tie_breaker(name: str, filename: str, fields: list[str], candidates: list[str]) -> str | None:
    settings = get_settings()
    if not settings.ENABLE_LOCAL_LLM_CLASSIFICATION or not candidates:
        return None
    # Only metadata is sent to an explicitly local Ollama endpoint; no feature values or records.
    prompt = (
        "Classify this geospatial dataset using only the metadata below. Choose exactly one label "
        f"from {candidates}. Reply with only JSON {{\"source_type\":\"label\"}}. "
        f"Name: {name[:160]}. File: {filename[:160]}. Fields: {fields[:80]}"
    )
    body = json.dumps({"model": settings.LOCAL_LLM_MODEL, "prompt": prompt, "stream": False, "format": "json"}).encode()
    request = Request(settings.LOCAL_LLM_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=4) as response:
            result = json.loads(response.read().decode())
        answer = json.loads(result.get("response", "{}"))
        suggestion = answer.get("source_type")
        return suggestion if suggestion in candidates else None
    except Exception:
        return None


def classify_source_type(name: str, filename: str, fields: list[str] | None = None,
                         geometry_types: list[str] | None = None) -> dict:
    """Recommend a source type from metadata, without inspecting property values."""
    fields = [str(field).strip().lower().replace(" ", "_") for field in (fields or [])]
    geometry_types = [str(value).lower() for value in (geometry_types or [])]
    haystack = f"{name} {filename}".lower().replace("_", " ").replace("-", " ")
    scores = {source_type: 0.0 for source_type in SOURCE_TYPES}
    reasons: dict[str, list[str]] = {source_type: [] for source_type in SOURCE_TYPES}

    for source_type, phrases in RULES.items():
        for phrase in phrases:
            if phrase in haystack:
                scores[source_type] += 2.0
                reasons[source_type].append(f"name contains '{phrase}'")
    field_set = set(fields)
    for source_type, cues in FIELD_CUES.items():
        matched = field_set & cues
        if matched:
            scores[source_type] += min(3.0, len(matched) * 1.5)
            reasons[source_type].append(f"fields match {', '.join(sorted(matched))}")

    if any(value in {"linestring", "multilinestring"} for value in geometry_types):
        scores["utility"] += 1.0
        reasons["utility"].append("line geometry")
    if any(value in {"polygon", "multipolygon"} for value in geometry_types):
        scores["cadastral"] += 0.5
        scores["municipal"] += 0.5
    if filename.lower().endswith((".tif", ".tiff")) and not any(scores[t] for t in ("drone", "orthoimagery", "dsm", "dtm")):
        return {"source_type": None, "confidence": 0.0, "method": "rules", "needs_review": True,
                "reason": "Raster format alone cannot distinguish imagery, DSM, or DTM."}

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_type, best_score = ranked[0]
    second_score = ranked[1][1]
    if best_score <= 0:
        return {"source_type": None, "confidence": 0.0, "method": "rules", "needs_review": True,
                "reason": "No reliable filename or schema cues found; select a source type manually."}

    confidence = min(0.95, 0.45 + 0.1 * best_score + 0.08 * max(0.0, best_score - second_score))
    method = "rules"
    ambiguous = best_score - second_score < 1.5
    if ambiguous:
        suggestion = _local_llm_tie_breaker(name, filename, fields, [item[0] for item in ranked[:3]])
        if suggestion:
            best_type, method = suggestion, "rules+local_llm"
            confidence = min(confidence, 0.7)  # LLM suggestions are deliberately kept review-only.
        else:
            return {"source_type": None, "confidence": round(confidence, 2), "method": "rules",
                    "needs_review": True,
                    "reason": "Several source types match equally well; select one manually or enable a local LLM tie-breaker."}
    return {
        "source_type": best_type,
        "confidence": round(confidence, 2),
        "method": method,
        "needs_review": True,
        "reason": "; ".join(reasons[best_type]) or "metadata classification suggestion",
    }
