"""
Reusable geometry helper functions: area, centroid, distance, and overlap
calculations. Shared by the matcher, topology validator, and conflict
detector.

GIS correctness note: all metric (area/overlap) calculations reproject
geometries into an appropriate LOCAL UTM zone computed from the
geometry's own centroid -- never using raw lat/lon degrees as if they
were meters, and never assuming a single hardcoded UTM zone regardless
of where the data actually is. Centroid-to-centroid distance uses the
haversine great-circle formula, which is the correct approach for that
specific calculation (no projection needed for a single distance).
"""
from typing import Tuple, Optional
from shapely.geometry.base import BaseGeometry
from pyproj import Transformer, CRS
from shapely.ops import transform as shapely_transform
import math
from functools import lru_cache


def get_utm_epsg(lon: float, lat: float) -> str:
    """
    Compute the correct UTM EPSG code for a given lon/lat, instead of
    assuming a single fixed zone. WGS84 UTM zones: EPSG:326xx (Northern
    Hemisphere) / EPSG:327xx (Southern Hemisphere), where xx is the
    1-60 UTM zone number.
    """
    zone = int((lon + 180) / 6) + 1
    zone = max(1, min(60, zone))
    hemisphere_prefix = 326 if lat >= 0 else 327
    return f"EPSG:{hemisphere_prefix}{zone:02d}"


@lru_cache(maxsize=32)
def _transformer(source_crs: str, metric_crs: str):
    return Transformer.from_crs(CRS.from_user_input(source_crs), CRS.from_user_input(metric_crs), always_xy=True)


def _to_metric_with_crs(geom: BaseGeometry, source_crs: str, metric_crs: str) -> BaseGeometry:
    """Reproject a geometry from source_crs into a specific metric_crs."""
    if geom is None or geom.is_empty:
        return geom
    try:
        src = CRS.from_user_input(source_crs)
        if src.is_projected:
            # Already in a projected (metric-like) CRS; assume it's usable as-is.
            return geom
        transformer = _transformer(source_crs, metric_crs)
        return shapely_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
    except Exception:
        return geom


def to_metric(geom: BaseGeometry, source_crs: str = "EPSG:4326") -> BaseGeometry:
    """
    Project a single geometry to the correct local UTM zone (derived from
    its own centroid), so area is expressed in meters, not degrees.
    """
    if geom is None or geom.is_empty:
        return geom
    try:
        centroid = geom.centroid
        metric_crs = get_utm_epsg(centroid.x, centroid.y)
        return _to_metric_with_crs(geom, source_crs, metric_crs)
    except Exception:
        return geom


def area_sqm(geom: BaseGeometry, source_crs: str = "EPSG:4326") -> float:
    if geom is None or geom.is_empty:
        return 0.0
    metric_geom = to_metric(geom, source_crs)
    return abs(metric_geom.area)


def centroid_latlon(geom: BaseGeometry) -> Tuple[Optional[float], Optional[float]]:
    if geom is None or geom.is_empty:
        return None, None
    c = geom.centroid
    return c.y, c.x  # lat, lon (assumes geom is already in EPSG:4326)


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two lat/lon points. This is
    the geodetically correct approach for a single point-to-point distance
    and does not require projection."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def iou(geom_a: BaseGeometry, geom_b: BaseGeometry, source_crs: str = "EPSG:4326") -> float:
    """
    Intersection-over-Union for two geometries, computed in a SHARED local
    metric (UTM) CRS chosen from geom_a's centroid, so both shapes are
    compared in the same, consistent projected space. Returns 0.0 for
    empty/invalid geometries or non-overlapping shapes.
    """
    if geom_a is None or geom_b is None or geom_a.is_empty or geom_b.is_empty:
        return 0.0
    try:
        centroid = geom_a.centroid
        metric_crs = get_utm_epsg(centroid.x, centroid.y)
        a = _to_metric_with_crs(geom_a, source_crs, metric_crs)
        b = _to_metric_with_crs(geom_b, source_crs, metric_crs)
        if not a.is_valid:
            a = a.buffer(0)
        if not b.is_valid:
            b = b.buffer(0)
        inter = a.intersection(b).area
        union = a.union(b).area
        if union <= 0:
            return 0.0
        return max(0.0, min(1.0, inter / union))
    except Exception:
        return 0.0


def point_in_polygon_proximity(point_geom: BaseGeometry, polygon_geom: BaseGeometry,
                                source_crs: str = "EPSG:4326", decay_m: float = 50.0) -> float:
    """
    A distance-decay 'overlap-like' score for point-vs-polygon comparisons
    (e.g. GNSS point vs cadastral parcel), computed in a shared local UTM
    zone chosen from the polygon's centroid (the more stable reference).
    Returns 1.0 if the point is inside the polygon, decaying toward 0 as
    distance from the boundary grows, using decay_m as the characteristic
    decay distance in meters.
    """
    if point_geom is None or polygon_geom is None or point_geom.is_empty or polygon_geom.is_empty:
        return 0.0
    try:
        centroid = polygon_geom.centroid
        metric_crs = get_utm_epsg(centroid.x, centroid.y)
        p = _to_metric_with_crs(point_geom, source_crs, metric_crs)
        poly = _to_metric_with_crs(polygon_geom, source_crs, metric_crs)
        if poly.contains(p):
            return 1.0
        dist = poly.distance(p)
        return max(0.0, math.exp(-dist / decay_m))
    except Exception:
        return 0.0
