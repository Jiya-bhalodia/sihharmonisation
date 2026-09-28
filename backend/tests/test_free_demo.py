from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from app.config import Settings
from app.security import ROLE_PERMISSIONS, require_permission
from app.services.free_demo import preflight_upload, require_job_type


POSTGRES_URL = "postgresql+psycopg://demo:unused@db.example.test:5432/demo"


def free_settings(**overrides):
    values = {"FREE_DEMO_MODE": True, "DATABASE_URL": POSTGRES_URL}
    values.update(overrides)
    return Settings(**values)


def test_free_demo_defaults_off_and_existing_local_mode_is_unchanged():
    defaults = Settings()
    assert defaults.FREE_DEMO_MODE is False
    assert defaults.is_local_demo_mode is True
    assert defaults.sqlalchemy_url.startswith("sqlite:")

    production = Settings(DEMO_MODE=False, DATABASE_URL=POSTGRES_URL)
    assert production.FREE_DEMO_MODE is False
    assert production.sqlalchemy_url == POSTGRES_URL


def test_free_demo_never_selects_sqlite_and_keeps_authentication_enabled():
    settings = free_settings(DEMO_MODE=True)
    assert settings.sqlalchemy_url == POSTGRES_URL
    assert settings.AUTH_ENABLED is True
    with pytest.raises(ValidationError, match="AUTH_ENABLED"):
        free_settings(AUTH_ENABLED=False)
    with pytest.raises(ValidationError, match="PostgreSQL"):
        free_settings(DATABASE_URL="sqlite:///unsafe.db")


def test_postgresql_urls_always_select_the_installed_psycopg_v3_driver():
    for configured_url in (
        "postgresql://demo:unused@db.example.test:5432/demo",
        "postgres://demo:unused@db.example.test:5432/demo",
        "postgresql+psycopg2://demo:unused@db.example.test:5432/demo",
        POSTGRES_URL,
    ):
        settings = Settings(DEMO_MODE=False, DATABASE_URL=configured_url)
        assert settings.sqlalchemy_url.startswith("postgresql+psycopg://")

    hosted = free_settings(DATABASE_URL="postgresql://demo:unused@db.example.test:5432/demo")
    assert hosted.sqlalchemy_url.startswith("postgresql+psycopg://")


def test_free_demo_rejects_enabled_local_models():
    with pytest.raises(ValidationError, match="Local models"):
        free_settings(ENABLE_LOCAL_EMBEDDINGS=True)


def test_only_allowlisted_lightweight_vector_job_is_accepted():
    require_job_type("vector_harmonization", free_settings())
    with pytest.raises(HTTPException, match="422"):
        require_job_type("raster_inspection", free_settings())


def test_upload_limit_and_feature_limit_are_enforced():
    settings = free_settings(FREE_DEMO_MAX_UPLOAD_MB=1, FREE_DEMO_MAX_FEATURES=1)
    payload = b'{"type":"FeatureCollection","features":[]}'
    assert preflight_upload("small.geojson", payload, settings) == (0, 0)
    with pytest.raises(HTTPException) as error:
        preflight_upload("large.geojson", b"x" * (1024 * 1024 + 1), settings)
    assert error.value.status_code == 413


def test_invalid_file_type_and_feature_count_are_rejected():
    settings = free_settings(FREE_DEMO_MAX_FEATURES=1)
    with pytest.raises(HTTPException) as error:
        preflight_upload("map.tif", b"not-a-raster", settings)
    assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error:
        preflight_upload("records.exe", b"x", settings)
    assert error.value.status_code == 422
    geojson = b'{"type":"FeatureCollection","features":[{},{}]}'
    with pytest.raises(HTTPException) as error:
        preflight_upload("records.geojson", geojson, settings)
    assert error.value.status_code == 413


def test_evaluator_is_read_only_and_cannot_access_privileged_actions():
    assert "evaluator" in ROLE_PERMISSIONS
    for permission in ("review", "export", "datasets:delete", "users:manage", "upload:cadastral"):
        with pytest.raises(HTTPException) as error:
            require_permission(SimpleNamespace(role="evaluator"), permission)
        assert error.value.status_code == 403
    require_permission(SimpleNamespace(role="administrator"), "review")
    require_permission(SimpleNamespace(role="evaluator"), "harmonize:free_demo")

    # Check an actual mutating route's authorization guard, before it touches the DB.
    from app.api.conflicts import resolve_conflict
    from starlette.requests import Request
    request = Request({"type": "http", "method": "POST", "path": "/api/conflicts/x/resolve",
                       "headers": [], "client": ("127.0.0.1", 1234), "query_string": b""})
    with pytest.raises(HTTPException) as error:
        resolve_conflict("missing", SimpleNamespace(status="Resolved"), request, object(),
                         SimpleNamespace(role="evaluator"))
    assert error.value.status_code == 403


def test_free_demo_evaluator_can_run_only_explicit_bounded_harmonization_permission(monkeypatch):
    import app.api.harmonize as api

    class FakeDB:
        def commit(self): pass
        def refresh(self, _value): pass

    job = SimpleNamespace(id="job-1", status="completed", total_processed=1)
    monkeypatch.setattr(api, "settings", SimpleNamespace(is_local_demo_mode=False, FREE_DEMO_MODE=True,
                                                           FREE_DEMO_MAX_PROCESSING_SECONDS=20))
    job_types = []
    monkeypatch.setattr(api, "require_job_type", lambda job_type, _settings: job_types.append(job_type))
    monkeypatch.setattr(api, "ensure_existing_capacity", lambda *_args: None)
    monkeypatch.setattr(api, "run_harmonization", lambda *_args, **_kwargs: job)
    monkeypatch.setattr(api, "_add_pilot_readiness_warning", lambda *_args: None)
    monkeypatch.setattr(api, "write_audit", lambda *_args, **_kwargs: None)

    from starlette.requests import Request
    request = Request({"type": "http", "method": "POST", "path": "/api/harmonize", "headers": [],
                       "client": ("127.0.0.1", 1234), "query_string": b""})
    result = api.trigger_harmonization(request, FakeDB(), SimpleNamespace(id="US_FREE_DEMO_EVALUATOR",
                                                                          email="demo@bhumi-x.local",
                                                                          role="evaluator"))
    assert result.status == "completed"
    assert job_types == ["vector_harmonization"]


def test_free_demo_requires_authentication(monkeypatch):
    from app.security import current_user
    from starlette.requests import Request

    monkeypatch.setattr("app.security.get_settings", lambda: free_settings())
    request = Request({"type": "http", "method": "GET", "path": "/api/parcels",
                       "headers": [], "client": ("127.0.0.1", 1234), "query_string": b""})
    with pytest.raises(HTTPException) as error:
        current_user(request, credentials=None, db=object())
    assert error.value.status_code == 401


def test_geometry_collection_complexity_is_counted():
    payload = (b'{"type":"FeatureCollection","features":[{"type":"Feature","geometry":'
               b'{"type":"GeometryCollection","geometries":[{"type":"Point","coordinates":[1,2]},'
               b'{"type":"Point","coordinates":[3,4]}]},"properties":{}}]}')
    assert preflight_upload("collection.geojson", payload, free_settings()) == (1, 2)


def test_r2_s3_endpoint_is_configurable_server_side():
    settings = free_settings(
        OBJECT_STORAGE_ENDPOINT="https://account.r2.cloudflarestorage.com",
        OBJECT_STORAGE_BUCKET="private-demo",
        OBJECT_STORAGE_ACCESS_KEY="server-side-only",
        OBJECT_STORAGE_SECRET_KEY="server-side-only",
    )
    assert settings.OBJECT_STORAGE_ENDPOINT.startswith("https://")
    assert settings.OBJECT_STORAGE_BUCKET == "private-demo"


def test_postgis_extension_schema_search_path_is_configured():
    from app.database import postgres_connect_args

    assert postgres_connect_args("extensions") == {"options": "-csearch_path=public,extensions"}


def test_local_health_endpoint_reports_liveness():
    from app.api.system import health_check

    result = health_check()
    assert result["status"] == "ok"
    assert "free_demo_mode" in result
    assert "disabled_features" in result


def test_free_demo_readiness_checks_postgres_redis_and_object_storage(monkeypatch):
    import redis
    import app.api.system as system

    class FakeConnection:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def execute(self, _query, _params=None):
            return SimpleNamespace(scalar=lambda: True)

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    class FakeRedis:
        def __init__(self, *_args, **_kwargs): pass
        def ping(self): return True
        def close(self): pass

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_args): return None

    monkeypatch.setattr(system, "settings", SimpleNamespace(
        is_local_demo_mode=False, FREE_DEMO_MODE=True, POSTGIS_SCHEMA="extensions",
        REDIS_URL="rediss://example", OBJECT_STORAGE_ENDPOINT="https://r2.example",
        OBJECT_STORAGE_ACCESS_KEY="key", OBJECT_STORAGE_SECRET_KEY="secret",
        OBJECT_STORAGE_BUCKET="private-demo", SUPABASE_URL="https://project.example.test",
        SUPABASE_SERVICE_ROLE_KEY="server-side-only", SUPABASE_STORAGE_BUCKET="bhumi-x",
    ))
    monkeypatch.setattr(system, "engine", FakeEngine())
    monkeypatch.setattr(redis, "Redis", FakeRedis)
    monkeypatch.setattr(system, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert system.readiness_check() == {
        "status": "ready",
        "checks": {"postgres_postgis": True, "redis": True, "object_storage": True},
    }


def test_free_demo_vector_auto_job_does_not_import_or_dispatch_celery(monkeypatch):
    import builtins
    import app.services.auto_harmonization as auto
    import app.services.harmonization_service as harmonization

    expected_job = object()
    monkeypatch.setattr(auto, "get_settings", lambda: free_settings())
    monkeypatch.setattr(auto, "ensure_existing_capacity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(harmonization, "run_harmonization", lambda *_args, **_kwargs: expected_job)

    original_import = builtins.__import__
    def no_tasks_import(name, *args, **kwargs):
        if name == "app.tasks":
            raise AssertionError("Free demo tried to import the Celery task module")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_tasks_import)

    assert auto.create_auto_job(object()) is expected_job


def test_full_production_harmonization_still_queues_through_celery(monkeypatch):
    import sys
    import app.api.harmonize as api

    called = []
    fake_task = SimpleNamespace(delay=lambda *args: called.append(args))
    monkeypatch.setitem(sys.modules, "app.tasks", SimpleNamespace(run_harmonization_job=fake_task))
    monkeypatch.setattr(api, "settings", SimpleNamespace(is_local_demo_mode=False, FREE_DEMO_MODE=False))
    monkeypatch.setattr(api, "_add_pilot_readiness_warning", lambda *_args: None)
    monkeypatch.setattr(api, "write_audit", lambda *_args, **_kwargs: None)

    class FakeDB:
        def add(self, _value): pass
        def flush(self): pass
        def commit(self): pass
        def refresh(self, _value): pass

    from starlette.requests import Request
    request = Request({"type": "http", "method": "POST", "path": "/api/harmonize", "headers": [],
                       "client": ("127.0.0.1", 1234), "query_string": b""})
    user = SimpleNamespace(id="admin", email="admin@example.test", role="administrator")
    result = api.trigger_harmonization(request, FakeDB(), user)
    assert result.status == "queued"
    assert len(called) == 1
