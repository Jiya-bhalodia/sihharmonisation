"""Persist source uploads separately from relational metadata."""
import hashlib
import io
import os
from pathlib import Path

from app.config import get_settings


def store_original(dataset_id: str, filename: str, content: bytes) -> str:
    return store_original_stream(dataset_id, filename, io.BytesIO(content))


def store_original_stream(dataset_id: str, filename: str, stream) -> str:
    settings = get_settings()
    safe_name = os.path.basename(filename).replace(" ", "_")
    key = f"originals/{dataset_id}/{safe_name}"
    digest = hashlib.sha256()
    stream.seek(0)
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    checksum = digest.hexdigest()
    stream.seek(0)
    if not settings.is_local_demo_mode:
        if not settings.OBJECT_STORAGE_BUCKET:
            raise RuntimeError("OBJECT_STORAGE_BUCKET is required for production uploads")
        try:
            import boto3
        except ImportError as error:
            raise RuntimeError("boto3 is required for production object storage") from error
        client = boto3.client(
            "s3", endpoint_url=settings.OBJECT_STORAGE_ENDPOINT or None,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY or None,
            region_name=os.getenv("AWS_DEFAULT_REGION") or None,
        )
        client.upload_fileobj(stream, settings.OBJECT_STORAGE_BUCKET, key,
                              ExtraArgs={"Metadata": {"sha256": checksum, "original-filename": safe_name}})
        return f"s3://{settings.OBJECT_STORAGE_BUCKET}/{key}"
    root = Path(settings.DATA_DIR).resolve() / "originals" / dataset_id
    root.mkdir(parents=True, exist_ok=True)
    target = root / safe_name
    with target.open("wb") as output:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    return f"file://{target}#sha256={checksum}"
