"""Optional, offline multilingual text embeddings for match corroboration."""
from functools import lru_cache
import logging
from contextvars import ContextVar

from app.config import get_settings

logger = logging.getLogger("services.embeddings")
_embedding_comparisons: ContextVar[int] = ContextVar("embedding_comparisons", default=0)


def reset_embedding_metrics() -> None:
    _embedding_comparisons.set(0)


def embedding_metrics_summary() -> str:
    """Describe actual E5 use in the current harmonization context."""
    settings = get_settings()
    if not settings.ENABLE_LOCAL_EMBEDDINGS:
        return "Local E5 embeddings are disabled; text matching used fuzzy similarity."
    count = _embedding_comparisons.get()
    if count:
        return (f"Local multilingual E5 embeddings contributed to {count} text comparisons, blended 35% "
                "with fuzzy similarity; parcel and survey identifiers stayed non-semantic.")
    if _model.cache_info().currsize and _model() is None:
        return "E5 could not load from the local cache; text matching fell back to fuzzy similarity."
    return "E5 was enabled, but no eligible shared text attributes needed embeddings in this run."


@lru_cache(maxsize=1)
def _model():
    settings = get_settings()
    if not settings.ENABLE_LOCAL_EMBEDDINGS:
        return None
    try:
        from sentence_transformers import SentenceTransformer
        # Local-only loading prevents silent network calls or paid inference.
        return SentenceTransformer(settings.LOCAL_EMBEDDING_MODEL, local_files_only=True)
    except Exception as error:
        logger.warning("Local embeddings unavailable; fuzzy matching remains active (%s)", error)
        return None


@lru_cache(maxsize=50000)
def _encode(text: str, role: str):
    model = _model()
    if model is None:
        return None
    try:
        vector = model.encode(
            [f"{role}: {text}"], normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return tuple(float(value) for value in vector)
    except Exception as error:
        logger.warning("Could not embed a match attribute; using fuzzy comparison (%s)", error)
        return None


def local_text_similarity(first: str, second: str) -> float | None:
    """Return cached cosine similarity, or None when local model support is disabled."""
    if not first.strip() or not second.strip():
        return None
    left = _encode(first.strip().lower(), "query")
    right = _encode(second.strip().lower(), "passage")
    if left is None or right is None or len(left) != len(right):
        return None
    # Embeddings are normalized on encode, so their dot product is cosine.
    cosine = sum(a * b for a, b in zip(left, right))
    _embedding_comparisons.set(_embedding_comparisons.get() + 1)
    return max(0.0, min(1.0, cosine))
