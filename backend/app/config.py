"""
Central configuration for BHUMI-X backend.
Loads from environment variables (.env) with sensible demo defaults.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "BHUMI-X"
    APP_VERSION: str = "1.1.0"

    DEMO_MODE: bool = True
    SQLITE_PATH: str = "./bhumix_demo.db"
    DATABASE_URL: str = "postgresql+psycopg://bhumix:bhumix@localhost:5432/bhumix"

    DATA_DIR: str = "../data"
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    TARGET_CRS: str = "EPSG:4326"
    MATCH_MAX_DISTANCE_M: float = 75.0

    # Weighted spatial matching model weights (must sum to 1.0).
    # Proximity and geometry overlap are weighted equally and highest
    # because they are the strongest independent signals that two records
    # describe the same real-world parcel; area and attribute similarity
    # are weighted equally as corroborating (but individually weaker)
    # evidence, since area can be legitimately reported differently across
    # departments and attributes are often incomplete.
    WEIGHT_SPATIAL_PROXIMITY: float = 0.30
    WEIGHT_GEOMETRY_OVERLAP: float = 0.30
    WEIGHT_AREA_SIMILARITY: float = 0.20
    WEIGHT_ATTRIBUTE_SIMILARITY: float = 0.20

    # Confidence bands
    CONFIDENCE_HIGH: float = 90.0
    CONFIDENCE_MEDIUM: float = 70.0

    # Schema mapping similarity threshold below which a field needs manual review
    SCHEMA_MAPPING_THRESHOLD: float = 0.55

    # Maximum accepted upload size, in megabytes, enforced at the API layer.
    # Large enough for a ward-scale GeoTIFF/orthomosaic.  City-scale imagery
    # should be registered as a COG/object-store asset in production rather
    # than posted through a single HTTP request.
    MAX_UPLOAD_SIZE_MB: int = 250

    LOG_LEVEL: str = "INFO"

    @property
    def sqlalchemy_url(self) -> str:
        if self.DEMO_MODE:
            return f"sqlite:///{self.SQLITE_PATH}"
        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
