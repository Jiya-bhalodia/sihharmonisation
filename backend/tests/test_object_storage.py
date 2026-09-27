import hashlib
import io
import sys
from types import SimpleNamespace

from app import object_storage


def test_free_demo_uploads_to_supabase_storage_without_network(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["body"] = request.data
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(object_storage, "get_settings", lambda: SimpleNamespace(
        FREE_DEMO_MODE=True,
        is_local_demo_mode=False,
        SUPABASE_URL="https://project.example.test/",
        SUPABASE_SERVICE_ROLE_KEY="test-service-role-key",
        SUPABASE_STORAGE_BUCKET="bhumi-x",
    ))
    monkeypatch.setattr(object_storage, "urlopen", fake_urlopen)

    result = object_storage.store_original_stream("DS-123", "parcel map.geojson", io.BytesIO(b"sample"))

    checksum = hashlib.sha256(b"sample").hexdigest()
    assert captured["url"] == (
        "https://project.example.test/storage/v1/object/bhumi-x/"
        "originals/DS-123/parcel_map.geojson"
    )
    assert captured["headers"]["authorization"] == "Bearer test-service-role-key"
    assert captured["headers"]["apikey"] == "test-service-role-key"
    assert captured["body"] == b"sample"
    assert result == f"supabase://bhumi-x/originals/DS-123/parcel_map.geojson#sha256={checksum}"


def test_full_deployment_keeps_existing_s3_upload_path(monkeypatch):
    captured = {}

    class FakeS3:
        def upload_fileobj(self, stream, bucket, key, ExtraArgs):
            captured.update(bucket=bucket, key=key, body=stream.read(), extra=ExtraArgs)

    monkeypatch.setattr(object_storage, "get_settings", lambda: SimpleNamespace(
        FREE_DEMO_MODE=False,
        is_local_demo_mode=False,
        OBJECT_STORAGE_BUCKET="production-bucket",
        OBJECT_STORAGE_ENDPOINT="https://s3.example.test",
        OBJECT_STORAGE_ACCESS_KEY="access-placeholder",
        OBJECT_STORAGE_SECRET_KEY="secret-placeholder",
    ))
    monkeypatch.setattr(object_storage.os, "getenv", lambda _name: "us-east-1")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: FakeS3()))

    result = object_storage.store_original("DS-456", "parcel.geojson", b"sample")

    checksum = hashlib.sha256(b"sample").hexdigest()
    assert captured["bucket"] == "production-bucket"
    assert captured["key"] == "originals/DS-456/parcel.geojson"
    assert captured["body"] == b"sample"
    assert captured["extra"]["Metadata"]["sha256"] == checksum
    assert result == "s3://production-bucket/originals/DS-456/parcel.geojson"
