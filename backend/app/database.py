"""
Database engine/session setup for BHUMI-X.

Uses SQLite in DEMO_MODE (default, zero external dependencies) and is
compatible with PostgreSQL+PostGIS by simply setting DEMO_MODE=false and
DATABASE_URL in the environment -- no code changes required elsewhere,
because all queries go through SQLAlchemy Core/ORM.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.DEMO_MODE else {}

engine = create_engine(settings.sqlalchemy_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called once at app startup."""
    from app.models import orm  # noqa: F401 ensures models are registered
    Base.metadata.create_all(bind=engine)