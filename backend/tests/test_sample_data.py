from pathlib import Path

from app.sample_data import REQUIRED_SAMPLE_FILES, resolve_sample_data_dir


def test_render_layout_resolves_packaged_fixtures_when_override_is_stale(tmp_path: Path):
    app_dir = tmp_path / "app" / "app"
    app_dir.mkdir(parents=True)
    fixture_dir = tmp_path / "app" / "data" / "sample"
    fixture_dir.mkdir(parents=True)
    for filename in REQUIRED_SAMPLE_FILES:
        (fixture_dir / filename).write_text("fixture")

    resolved = resolve_sample_data_dir(app_dir, configured_dir="/data/sample")

    assert resolved.resolve() == fixture_dir.resolve()
