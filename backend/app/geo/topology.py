"""
Topology validation service using Shapely/GeoPandas.

Detects invalid geometries, self-intersections, duplicates, overlaps and
slivers, and produces safe corrections via make_valid / buffer(0) --
WITHOUT ever overwriting the original geometry. Both the original and the
corrected geometry are always retained (ValidationResult rows).
"""
from typing import List, Dict, Any
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid, explain_validity
from app.geo.geometry_utils import area_sqm
from app.utils.logger import get_logger

logger = get_logger("geo.topology")

SLIVER_AREA_RATIO_THRESHOLD = 0.02  # perimeter^2/area ratio heuristic threshold


def validate_geometry(geom: BaseGeometry) -> Dict[str, Any]:
    """
    Validate a single geometry. Returns a dict describing validity,
    issue type, and (if applicable) a corrected geometry.
    """
    result = {
        "is_valid": True,
        "issue_type": "none",
        "corrected_geometry": None,
        "corrected": False,
        "explanation": "",
    }

    if geom is None or geom.is_empty:
        result["is_valid"] = False
        result["issue_type"] = "missing_geometry"
        result["explanation"] = "Geometry is missing or empty"
        return result

    if not geom.is_valid:
        reason = explain_validity(geom)
        result["is_valid"] = False
        result["explanation"] = reason
        if "Self-intersection" in reason:
            result["issue_type"] = "self_intersection"
        else:
            result["issue_type"] = "invalid_geometry"
        try:
            fixed = make_valid(geom)
            result["corrected_geometry"] = fixed
            result["corrected"] = True
        except Exception as e:
            logger.error(f"make_valid failed: {e}")
        return result

    # Sliver detection: very thin polygons with high perimeter-to-area ratio
    if geom.geom_type in ("Polygon", "MultiPolygon") and geom.area > 0:
        try:
            perimeter = geom.length
            compactness = (perimeter ** 2) / geom.area if geom.area > 0 else float("inf")
            # A perfect circle has compactness ~= 4*pi (~12.57); slivers are far higher
            if compactness > 200:
                result["issue_type"] = "sliver"
                result["explanation"] = f"High perimeter/area compactness ratio ({compactness:.1f}) suggests a sliver polygon"
        except Exception:
            pass

    return result


def detect_duplicates(geometries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Given a list of {id, geometry} dicts, flag geometries that are
    near-identical (equals_exact within tolerance or very high IoU).
    Returns a list of duplicate-pair issue dicts.
    """
    from app.geo.geometry_utils import iou

    issues = []
    n = len(geometries)
    for i in range(n):
        for j in range(i + 1, n):
            g1, g2 = geometries[i], geometries[j]
            geom1, geom2 = g1.get("geometry"), g2.get("geometry")
            if geom1 is None or geom2 is None or geom1.is_empty or geom2.is_empty:
                continue
            if geom1.geom_type != geom2.geom_type:
                continue
            try:
                overlap = iou(geom1, geom2)
                if overlap > 0.97:
                    issues.append({
                        "type": "duplicate",
                        "feature_a": g1.get("id"),
                        "feature_b": g2.get("id"),
                        "iou": overlap,
                    })
            except Exception:
                continue
    return issues


def detect_overlaps(geometries: List[Dict[str, Any]], min_overlap_ratio: float = 0.05) -> List[Dict[str, Any]]:
    """
    Detect meaningful (non-duplicate, non-trivial) overlaps between polygons
    from the SAME layer (e.g. two parcels overlapping each other).
    """
    from app.geo.geometry_utils import iou

    issues = []
    n = len(geometries)
    for i in range(n):
        for j in range(i + 1, n):
            g1, g2 = geometries[i], geometries[j]
            geom1, geom2 = g1.get("geometry"), g2.get("geometry")
            if geom1 is None or geom2 is None or geom1.is_empty or geom2.is_empty:
                continue
            try:
                overlap = iou(geom1, geom2)
                if min_overlap_ratio < overlap <= 0.97:
                    issues.append({
                        "type": "overlap",
                        "feature_a": g1.get("id"),
                        "feature_b": g2.get("id"),
                        "iou": overlap,
                    })
            except Exception:
                continue
    return issues