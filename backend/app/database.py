"""
Database engine/session setup for BHUMI-X.

Uses SQLite in the local DEMO_MODE. FREE_DEMO_MODE always uses PostgreSQL
and configures the connection search_path for Supabase's dedicated PostGIS
schema while leaving the standard public-schema deployment as the default.
"""
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings
from pathlib import Path

settings = get_settings()

def postgres_connect_args(postgis_schema: str) -> dict:
    """Search public application tables and the configured PostGIS schema."""
    return {"options": f"-csearch_path=public,{postgis_schema}"}


if settings.is_local_demo_mode:
    connect_args = {"check_same_thread": False}
else:
    # Keep public first for BHUMI-X tables and add the PostGIS extension
    # schema so unqualified geometry types/functions in ORM and migrations
    # resolve on Supabase and ordinary PostgreSQL deployments.
    connect_args = postgres_connect_args(settings.POSTGIS_SCHEMA)

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
    if engine.dialect.name == "postgresql":
        schema = settings.POSTGIS_SCHEMA
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            extension_schema = connection.execute(text(
                "SELECT n.nspname FROM pg_extension e "
                "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'postgis'"
            )).scalar_one_or_none()
            if extension_schema and extension_schema != schema:
                raise RuntimeError(
                    f"PostGIS is installed in schema '{extension_schema}', but POSTGIS_SCHEMA is '{schema}'. "
                    "Set POSTGIS_SCHEMA to the installed schema or configure the extension before startup."
                )
            if not extension_schema:
                connection.execute(text(f'CREATE EXTENSION postgis WITH SCHEMA "{schema}"'))
    Base.metadata.create_all(bind=engine)
    # create_all does not add columns to an existing local SQLite demo file.
    # Keep the small provenance addition compatible with that persistent file.
    if engine.dialect.name == "sqlite" and "provenance" not in {
        column["name"] for column in inspect(engine).get_columns("datasets")
    }:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE datasets ADD COLUMN provenance VARCHAR(80) NOT NULL DEFAULT 'user_upload'"
            ))
    if engine.dialect.name == "postgresql":
        run_postgres_migrations()
    if not get_settings().is_local_demo_mode:
        ensure_bootstrap_admin()


def ensure_bootstrap_admin():
    settings = get_settings()
    if not settings.AUTH_ENABLED:
        raise RuntimeError("AUTH_ENABLED must remain true in production deployments")
    if len(settings.AUTH_SECRET_KEY) < 32:
        raise RuntimeError("AUTH_SECRET_KEY must be set to a random value of at least 32 characters in production")
    if not settings.BOOTSTRAP_ADMIN_EMAIL or not settings.BOOTSTRAP_ADMIN_PASSWORD:
        raise RuntimeError("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD for the initial administrator")
    from app.models.orm import User
    from app.security import hash_password
    email = settings.BOOTSTRAP_ADMIN_EMAIL.strip().lower()
    with SessionLocal() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            return
        try:
            password_hash = hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD)
        except ValueError as error:
            raise RuntimeError(f"Invalid bootstrap administrator password: {error}")
        db.add(User(id="US_BOOTSTRAP_ADMIN", email=email, full_name="Initial Administrator",
                    role="administrator", password_hash=password_hash, is_active=True))
        db.commit()


def run_postgres_migrations():
    """Apply numbered, transactional SQL migrations exactly once."""
    migration_dir = Path(__file__).resolve().parents[1] / "migrations" / "postgres"
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(120) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
        for migration in sorted(migration_dir.glob("*.sql")):
            if migration.name in applied:
                continue
            # Do not split semicolons inside PostgreSQL dollar-quoted functions.
            for statement in _split_sql(migration.read_text()):
                if statement.strip():
                    connection.execute(text(statement))
            connection.execute(text("INSERT INTO schema_migrations (version) VALUES (:version)"), {"version": migration.name})


def _split_sql(script: str) -> list[str]:
    statements, current = [], []
    in_dollar_quote = False
    index = 0
    while index < len(script):
        if script.startswith("$$", index):
            in_dollar_quote = not in_dollar_quote
            current.append("$$")
            index += 2
            continue
        char = script[index]
        if char == ";" and not in_dollar_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements
