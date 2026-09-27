"""
AI Spatial Matching engine.

Matches equivalent real-world features across independently-sourced
datasets (cadastral parcel <-> municipal building <-> revenue record <->
GNSS point <-> ground truth) using a real, explainable, weighted scoring
model built from four independently computed sub-scores:

    spatial_proximity    - centroid distance decay (haversine)
    geometry_overlap      - IoU in a locally-correct UTM zone (or
                             point-in-polygon distance decay)
    area_similarity        - relative area difference
    attribute_similarity - fuzzy string similarity across shared canonical fields

Nothing here is hardcoded per-feature; every score is derived from the
actual geometry/attributes of the two candidate features being compared.
No feature -- including an "anchor" record -- is ever assigned a literal
placeholder confidence; a feature with no cross-source match simply has
no match score, rather than a fabricated 100%.
"""
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from app.services.embedding_service import local_text_similarity
from app.geo.geometry_utils import (
    haversine_distance_m, iou, point_in_polygon_proximity
)
from app.config import get_settings

settings = get_settings()

ATTRIBUTE_FIELDS_FOR_COMPARISON = ["owner_name", "land_use", "parcel_id", "survey_number", "address"]
IDENTIFIER_FIELDS = {"parcel_id", "survey_number"}


@dataclass
class MatchCandidate:
    feature_id: str
    dataset_id: str
    canonical_type: str
    geometry: Any
    centroid_lat: Optional[float]
    centroid_lon: Optional[float]
    area: Optional[float]
    properties: Dict[str, Any] = field(default_factory=dict)
    # The originating dataset's department source_type (cadastral, revenue,
    # municipal, gnss, ground_truth, utility, drone). Used so the matching
    # engine can distinguish the authoritative geometry source (cadastral)
    # from corroborating sources, rather than treating every "parcel"
    # canonical_type record as an equally-valid anchor.
    source_type: str = "unknown"


def _attribute_similarity(props_a: Dict[str, Any], props_b: Dict[str, Any]) -> float:
    shared_scores = []
    for field_name in ATTRIBUTE_FIELDS_FOR_COMPARISON:
        va, vb = props_a.get(field_name), props_b.get(field_name)
        if va is None or vb is None:
            continue
        va_str, vb_str = str(va).strip().lower(), str(vb).strip().lower()
        if not va_str or not vb_str:
            continue
        fuzzy_score = SequenceMatcher(None, va_str, vb_str).ratio()
        if field_name not in IDENTIFIER_FIELDS:
            embedding_score = local_text_similarity(va_str, vb_str)
            if embedding_score is not None:
                fuzzy_score = 0.65 * fuzzy_score + 0.35 * embedding_score
        shared_scores.append(fuzzy_score)
    if not shared_scores:
        return 0.5  # neutral score when no comparable attributes exist
    return sum(shared_scores) / len(shared_scores)


def _spatial_proximity_score(a: MatchCandidate, b: MatchCandidate, max_distance_m: float) -> float:
    if a.centroid_lat is None or b.centroid_lat is None:
        return 0.0
    dist = haversine_distance_m(a.centroid_lat, a.centroid_lon, b.centroid_lat, b.centroid_lon)
    return max(0.0, 1.0 - min(dist / max_distance_m, 1.0))


def _geometry_overlap_score(a: MatchCandidate, b: MatchCandidate) -> float:
    geom_a, geom_b = a.geometry, b.geometry
    if geom_a is None or geom_b is None or geom_a.is_empty or geom_b.is_empty:
        return 0.0

    a_is_polygon = geom_a.geom_type in ("Polygon", "MultiPolygon")
    b_is_polygon = geom_b.geom_type in ("Polygon", "MultiPolygon")

    if a_is_polygon and b_is_polygon:
        return iou(geom_a, geom_b)
    if a_is_polygon and not b_is_polygon:
        return point_in_polygon_proximity(geom_b, geom_a)
    if b_is_polygon and not a_is_polygon:
        return point_in_polygon_proximity(geom_a, geom_b)
    return 0.0


def _area_similarity_score(a: MatchCandidate, b: MatchCandidate) -> float:
    if not a.area or not b.area or a.area <= 0 or b.area <= 0:
        return 0.5  # neutral when one side has no area (e.g. GNSS point)
    diff_ratio = abs(a.area - b.area) / max(a.area, b.area)
    return max(0.0, 1.0 - diff_ratio)


def score_pair(a: MatchCandidate, b: MatchCandidate, max_distance_m: Optional[float] = None) -> Dict[str, float]:
    """
    Compute the full explainable score breakdown for a candidate pair.
    Returns percentages (0-100) for each sub-score plus the weighted overall.
    """
    max_distance_m = max_distance_m or settings.MATCH_MAX_DISTANCE_M

    proximity = _spatial_proximity_score(a, b, max_distance_m)
    overlap = _geometry_overlap_score(a, b)
    area_sim = _area_similarity_score(a, b)
    attr_sim = _attribute_similarity(a.properties, b.properties)

    overall = (
        settings.WEIGHT_SPATIAL_PROXIMITY * proximity +
        settings.WEIGHT_GEOMETRY_OVERLAP * overlap +
        settings.WEIGHT_AREA_SIMILARITY * area_sim +
        settings.WEIGHT_ATTRIBUTE_SIMILARITY * attr_sim
    )

    return {
        "spatial_proximity": round(proximity * 100, 1),
        "geometry_overlap": round(overlap * 100, 1),
        "area_similarity": round(area_sim * 100, 1),
        "attribute_similarity": round(attr_sim * 100, 1),
        "overall_confidence": round(max(0.0, min(1.0, overall)) * 100, 1),
    }


def find_candidate_matches(
    anchor: MatchCandidate,
    pool: List[MatchCandidate],
    max_distance_m: Optional[float] = None,
    min_confidence_pct: float = 40.0,
) -> List[Dict[str, Any]]:
    """
    Given an anchor feature and a pool of candidate features from OTHER
    datasets, return scored matches above the minimum confidence
    threshold, sorted best-first.
    """
    max_distance_m = max_distance_m or settings.MATCH_MAX_DISTANCE_M
    results = []
    for candidate in pool:
        if candidate.dataset_id == anchor.dataset_id:
            continue  # only match across different sources
        if anchor.centroid_lat is not None and candidate.centroid_lat is not None:
            dist = haversine_distance_m(anchor.centroid_lat, anchor.centroid_lon,
                                         candidate.centroid_lat, candidate.centroid_lon)
            if dist > max_distance_m * 3:
                continue  # cheap pre-filter before full scoring
        scores = score_pair(anchor, candidate, max_distance_m)
        if scores["overall_confidence"] >= min_confidence_pct:
            results.append({"candidate": candidate, "scores": scores})
    results.sort(key=lambda r: r["scores"]["overall_confidence"], reverse=True)
    return results


def confidence_band(pct: float) -> str:
    if pct >= settings.CONFIDENCE_HIGH:
        return "High"
    if pct >= settings.CONFIDENCE_MEDIUM:
        return "Medium"
    return "Low"
