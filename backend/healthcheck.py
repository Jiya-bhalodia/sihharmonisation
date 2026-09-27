"""Container health probe for the production backend's required services."""
import sys
import os

import boto3
from botocore.config import Config
from redis import Redis
from sqlalchemy import create_engine, text

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, socket_timeout=3)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        if not redis_client.ping():
            raise RuntimeError("Redis ping failed")

        object_store = boto3.client(
            "s3",
            endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY,
            region_name=os.getenv("AWS_DEFAULT_REGION") or None,
            config=Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 1}),
        )
        object_store.head_bucket(Bucket=settings.OBJECT_STORAGE_BUCKET)
    finally:
        redis_client.close()
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Backend dependency health check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
