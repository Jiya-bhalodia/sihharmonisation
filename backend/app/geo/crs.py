"""
CRS detection and transformation service using PyProj.

Handles the "CRS NORMALIZATION" stage of the harmonization pipeline:
detects a dataset's source CRS (or assumes a safe default), and
reprojects geometries to the platform's canonical target CRS
(EPSG:4326 by default) so all downstream spatial operations compare
apples to apples.
"""
from typing import Optional, Tuple
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry
from app.utils.logger import get_logger

logger = get_logger("geo.crs")

# Common CRSs seen in Indian urban/cadastral GIS workflows.
KNOWN_CRS_HINTS = {
    "utm43n": "EPSG:32643",
    "utm44n": "EPSG:32644",
    "wgs84": "EPSG:4326",
    "webmercator": "EPSG:3857",
}

DEFAULT_FALLBACK_CRS = "EPSG:4326"


def detect_crs(declared_crs: Optional[str], sample_coords: Optional[Tuple[float, float]] = None) -> str:
    """
    Attempt to determine a dataset's CRS.

    1. If a declared CRS string is present and pyproj can parse it, use it.
    2. Otherwise, heuristically inspect a sample coordinate: values in the
       range typical of UTM zone 43N (India) vs lat/lon degrees.
    3. Fall back to EPSG:4326 (assume already geographic) if unsure.
    """
    if declared_crs:
        try:
            CRS.from_user_input(declared_crs)
            return declared_crs
        except Exception:
            logger.warning(f"Could not parse declared CRS '{declared_crs}', falling back to heuristics")

    if sample_coords:
        x, y = sample_coords
        # Geographic coordinates: lon in [-180,180], lat in [-90,90]
        if -180 <= x <= 180 and -90 <= y <= 90:
            return "EPSG:4326"
        # UTM-like large numbers (meters), assume UTM 43N (covers much of central India)
        if 100000 <= x <= 999999 and 0 <= y <= 10000000:
            return "EPSG:32643"

    return DEFAULT_FALLBACK_CRS


def transform_geometry(geom: BaseGeometry, source_crs: str, target_crs: str = DEFAULT_FALLBACK_CRS) -> Tuple[BaseGeometry, str]:
    """
    Reproject a Shapely geometry from source_crs to target_crs.
    Returns (transformed_geometry, status) where status is 'transformed',
    'unchanged', or 'error'.
    """
    if not geom or geom.is_empty:
        return geom, "error"

    if source_crs == target_crs:
        return geom, "unchanged"

    try:
        transformer = Transformer.from_crs(CRS.from_user_input(source_crs), CRS.from_user_input(target_crs), always_xy=True)

        def _transform_coords(x, y, z=None):
            tx, ty = transformer.transform(x, y)
            return (tx, ty) if z is None else (tx, ty, z)

        from shapely.ops import transform as shapely_transform
        transformed = shapely_transform(_transform_coords, geom)
        return transformed, "transformed"
    except Exception as e:
        logger.error(f"CRS transform failed ({source_crs} -> {target_crs}): {e}")
        return geom, "error"


def geometry_to_geojson_str(geom: BaseGeometry) -> str:
    import json
    return json.dumps(mapping(geom))


def geojson_str_to_geometry(geojson_str: str) -> Optional[BaseGeometry]:
    import json
    try:
        return shape(json.loads(geojson_str))
    except Exception:
        return None