from shapely.geometry import Polygon
from types import SimpleNamespace

from app.geo.crs import geometry_to_geojson_str
from app.geo.topology import geometry_audit_snapshots
from app.ml.schema_mapper import preserve_manual_overrides
from app.services.harmonization_service import _topology_source_geometry


def test_geometry_audit_keeps_original_separate_from_correction():
    original = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
    original_geojson = geometry_to_geojson_str(original)
    corrected = original.buffer(0)

    audited_original, audited_correction = geometry_audit_snapshots(original_geojson, corrected)

    assert audited_original == original_geojson
    assert audited_correction == geometry_to_geojson_str(corrected)
    assert audited_original != audited_correction


def test_manual_mapping_override_survives_mapping_regeneration():
    generated = [{
        "source_field": "plot_ref", "canonical_field": "parcel_id",
        "confidence": 62.0, "method": "fuzzy_synonym",
    }]
    existing = [{
        "source_field": "plot_ref", "canonical_field": "survey_number",
        "manual_override": True,
    }]

    [mapping] = preserve_manual_overrides(generated, existing)

    assert mapping["canonical_field"] == "survey_number"
    assert mapping["confidence"] == 100.0
    assert mapping["manual_override"] is True
    assert mapping["method"] == "manual_override"


def test_generated_mapping_without_override_is_unchanged():
    generated = [{
        "source_field": "owner", "canonical_field": "owner_name",
        "confidence": 91.0, "method": "fuzzy_synonym",
    }]

    [mapping] = preserve_manual_overrides(generated, [])

    assert mapping["canonical_field"] == "owner_name"
    assert mapping["confidence"] == 91.0
    assert mapping["manual_override"] is False


def test_topology_rerun_uses_preserved_source_geometry():
    feature = SimpleNamespace(id="feature-1", geometry_geojson='{"type":"Polygon","coordinates":[]}')
    previous = {"original_geometry": '{"type":"Polygon","coordinates":[["source"]]}'}

    assert _topology_source_geometry(feature, {feature.id: previous}) == previous["original_geometry"]
    assert _topology_source_geometry(feature, {}) == feature.geometry_geojson
