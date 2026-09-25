"""
ID generation helpers for BHUMI-X entities.
"""
import uuid
import time


def new_id(prefix: str) -> str:
    """Generate a readable ID with enough entropy for city-scale imports.

    Six hexadecimal characters collide surprisingly often in a 29k-feature
    cadastral import. Twelve characters keeps IDs compact while giving a
    collision probability that is negligible for this application.
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def job_id() -> str:
    return f"JOB-{int(time.time())}-{uuid.uuid4().hex[:4]}"
