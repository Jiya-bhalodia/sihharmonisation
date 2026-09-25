"""
Simple structured logger used across BHUMI-X services.
"""
import logging
import sys
from app.config import get_settings

_settings = get_settings()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(_settings.LOG_LEVEL)
        logger.propagate = False
    return logger