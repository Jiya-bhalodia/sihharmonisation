"""Resolve the complete generated sample fixture set across repo/image layouts."""
import os
from pathlib import Path
from app.utils.logger import get_logger


logger = get_logger("sample_data")


REQUIRED_SAMPLE_FILES = (
    "cadastral_parcels.geojson",
    "revenue_records.geojson",
    "municipal_buildings.geojson",
    "ground_truth_points.geojson",
    "utility_lines.geojson",
    "gnss_survey_points.csv",
    "land_use.geojson",
    "hosted_demo_aoi.geojson",
)


def resolve_sample_data_dir(app_dir: Path, configured_dir: str | None = None) -> Path:
    """Find a directory containing every fixture needed by hosted startup.

    In the Render image `app_dir` is `/app/app`, making its parent `/app`,
    where the Dockerfile installs `data/sample`. In a source checkout a later
    candidate resolves to the repository-level `data/sample`.
    Incomplete or stale environment overrides are skipped.
    """
    configured = configured_dir if configured_dir is not None else os.environ.get("SAMPLE_DATA_DIR")
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.append(app_dir.parent / "data" / "sample")
    if len(app_dir.parents) > 1:
        candidates.append(app_dir.parents[1] / "data" / "sample")

    seen = set()
    diagnostics = []
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        exists = candidate.is_dir()
        filenames = sorted(path.name for path in candidate.iterdir()) if exists else []
        missing = [name for name in REQUIRED_SAMPLE_FILES if not (candidate / name).is_file()]
        if exists and not missing:
            return candidate
        diagnostics.append((candidate, exists, filenames, missing))

    checked = ", ".join(str(path) for path in seen)
    for candidate, exists, filenames, missing in diagnostics:
        logger.error("Sample fixture candidate: path=%s directory_exists=%s files=%s missing_required=%s",
                     candidate, exists, filenames, missing)
    missing_by_candidate = "; ".join(f"{path} missing={missing}" for path, _, _, missing in diagnostics)
    raise FileNotFoundError(
        f"Complete sample fixture directory not found; checked: {checked}; "
        f"missing required files by candidate: {missing_by_candidate}"
    )


def get_sample_data_dir() -> Path:
    return resolve_sample_data_dir(Path(__file__).resolve().parent)
