"""
Engine, session factory and the declarative Base.

`get_db` is the only way a request obtains a session. It always closes, and it
rolls back on an exception so a half-finished unit of work is never committed.
"""
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,      # survives a database restart without a stale-connection error
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


class Base(DeclarativeBase):
    """All models inherit this. Alembic autogenerate reads Base.metadata."""


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_connection() -> tuple[bool, str]:
    """Backs /health/db and the startup log. Never raises."""
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
        return True, str(version)
    except Exception as exc:      # noqa: BLE001 - reported to the caller, not swallowed
        return False, type(exc).__name__
