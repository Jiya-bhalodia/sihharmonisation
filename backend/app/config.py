"""
Central configuration for BHUMI-X backend.
Loads from environment variables (.env) with sensible demo defaults.
"""
from functools import lru_cache
import re
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "BHUMI-X"
    APP_VERSION: str = "1.1.0"

    DEMO_MODE: bool = True
    # Hosted, authenticated demo profile. Unlike DEMO_MODE, this always uses
    # PostgreSQL and never bypasses authentication or authorization.
    FREE_DEMO_MODE: bool = False
    FREE_DEMO_ALLOWED_JOB_TYPES: str = "vector_harmonization"
    FREE_DEMO_MAX_UPLOAD_MB: int = 2
    FREE_DEMO_MAX_DATASETS: int = 20
    FREE_DEMO_MAX_FEATURES: int = 1000
    FREE_DEMO_MAX_GEOMETRY_COMPLEXITY: int = 25000
    FREE_DEMO_MAX_PROCESSING_SECONDS: int = 20
    SQLITE_PATH: str = "./bhumix_demo.db"
    DATABASE_URL: str = ""
    POSTGIS_SCHEMA: str = "public"
    AUTH_ENABLED: bool = True
    LOAD_SAMPLE_DATA: bool = False
    AUTH_SECRET_KEY: str = ""
    AUTH_TOKEN_TTL_MINUTES: int = 720
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    OBJECT_STORAGE_ENDPOINT: str = ""
    OBJECT_STORAGE_BUCKET: str = "bhumix-originals"
    OBJECT_STORAGE_ACCESS_KEY: str = ""
    OBJECT_STORAGE_SECRET_KEY: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "bhumi-x"
    REDIS_URL: str = ""
    ASYNC_RASTER_THRESHOLD_MB: int = 32
    OCR_LANGUAGES: str = "eng+hin+mar"
    OCR_MAX_PAGES: int = 20
    OCR_DPI: int = 220
    ENABLE_LOCAL_EMBEDDINGS: bool = False
    LOCAL_EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"
    BUILDING_EXTRACTION_ENABLED: bool = False
    BUILDING_DETECTOR_MODEL: str = "IDEA-Research/grounding-dino-tiny"
    BUILDING_SEGMENTER_MODEL: str = "facebook/sam-vit-base"
    BUILDING_DETECTION_THRESHOLD: float = 0.32
    BUILDING_TILE_SIZE: int = 1024
    BUILDING_TILE_OVERLAP: int = 96
    ENABLE_LOCAL_LLM_CLASSIFICATION: bool = False
    LOCAL_LLM_URL: str = "http://127.0.0.1:11434/api/generate"
    LOCAL_LLM_MODEL: str = "llama3.2:3b"

    DATA_DIR: str = "../data"
    # An explicit path can be used when the worker's persistent disk is mounted
    # somewhere other than DATA_DIR/generated/previous_snapshot.json.
    CHANGE_SNAPSHOT_PATH: str = ""
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

    # Conservative initial hosted-staging request limit. The existing Docker
    # Compose deployment explicitly overrides this for its local workflow.
    MAX_UPLOAD_SIZE_MB: int = 50

    # Redis-backed fixed-window login limits.
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_IP_ATTEMPTS: int = 30
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 900

    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def validate_free_demo_settings(self):
        if self.FREE_DEMO_MODE:
            if not self.AUTH_ENABLED:
                raise ValueError("AUTH_ENABLED must be true when FREE_DEMO_MODE=true")
            if self.DATABASE_URL.lower().startswith("sqlite"):
                raise ValueError("FREE_DEMO_MODE requires PostgreSQL with PostGIS; SQLite is not supported")
            if any((self.ENABLE_LOCAL_EMBEDDINGS, self.BUILDING_EXTRACTION_ENABLED,
                    self.ENABLE_LOCAL_LLM_CLASSIFICATION)):
                raise ValueError("Local models must remain disabled when FREE_DEMO_MODE=true")
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", self.POSTGIS_SCHEMA or ""):
            raise ValueError("POSTGIS_SCHEMA must be a simple SQL identifier")
        if min(self.FREE_DEMO_MAX_UPLOAD_MB, self.FREE_DEMO_MAX_DATASETS, self.FREE_DEMO_MAX_FEATURES,
               self.FREE_DEMO_MAX_GEOMETRY_COMPLEXITY, self.FREE_DEMO_MAX_PROCESSING_SECONDS) <= 0:
            raise ValueError("FREE_DEMO resource limits must be positive")
        return self

    @property
    def is_local_demo_mode(self) -> bool:
        """SQLite/auth-bypassing demo mode, excluding the hosted free profile."""
        return self.DEMO_MODE and not self.FREE_DEMO_MODE

    @property
    def free_demo_allowed_jobs(self) -> frozenset[str]:
        return frozenset(item.strip() for item in self.FREE_DEMO_ALLOWED_JOB_TYPES.split(",") if item.strip())

    @property
    def sqlalchemy_url(self) -> str:
        if self.is_local_demo_mode:
            return f"sqlite:///{self.SQLITE_PATH}"
        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
