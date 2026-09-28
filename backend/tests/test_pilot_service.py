from types import SimpleNamespace

from app.services.pilot_service import evaluate_pilot_readiness


def dataset(identifier, source_type):
    return SimpleNamespace(id=identifier, source_type=source_type)


def feature(**properties):
    return SimpleNamespace(raw_properties=properties)


def test_readiness_blocks_missing_authoritative_inputs():
    report = evaluate_pilot_readiness([], {}, aoi_exists=False)
    assert report["status"] == "NOT_READY"
    assert report["blocker_count"] == 6
    assert {check["id"] for check in report["checks"] if check["status"] == "BLOCKER"} == {
        "aoi", "cadastral", "revenue", "municipal", "gnss", "imagery"
    }


def test_readiness_accepts_complete_technical_evidence():
    datasets = [
        dataset("cad", "cadastral"), dataset("rev", "revenue"), dataset("mun", "municipal"),
        dataset("gnss", "gnss"), dataset("ori", "orthoimagery"), dataset("util", "utility"),
        dataset("dsm", "dsm"),
    ]
    features = {
        "cad": [feature(cts_no="123")],
        "rev": [feature(survey_gat_no="123")],
        "mun": [feature(building_id="B1")],
        "gnss": [feature(horizontal_accuracy_m=0.02) for _ in range(10)],
        "ori": [feature(pixel_size=[0.1, 0.1])],
        "util": [feature(asset_id="U1")],
        "dsm": [feature(vertical_datum="MSL")],
    }
    report = evaluate_pilot_readiness(datasets, features, aoi_exists=True)
    assert report["status"] == "READY_FOR_REVIEW"
    assert report["blocker_count"] == 0


def test_free_demo_treats_missing_aoi_as_hosted_limitation():
    report = evaluate_pilot_readiness([], {}, aoi_exists=False, free_demo_mode=True)
    aoi = next(check for check in report["checks"] if check["id"] == "aoi")

    assert aoi["status"] == "LIMITATION"
    assert aoi["required"] is False
    assert "do not require an AOI" in aoi["detail"]
    assert "AOI-based clipping" in report["limitations"][-1]
