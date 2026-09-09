"""
Alembic environment.

The URL comes from app.core.config (and therefore from .env) rather than
alembic.ini, so there is exactly one place database credentials are configured.

One exception: a caller that supplies a URL explicitly wins. Either

    alembic -x db_url=postgresql+psycopg://... upgrade head

or, programmatically, `config.set_main_option("sqlalchemy.url", ...)` before
invoking the command. Without this the settings value was unconditionally
imposed, which meant a migration could never be run against a database other
than the one in .env - so the migrations could not be tested against a scratch
database, and an operator upgrading staging had to edit their environment first.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base

# Importing the model registry is what makes autogenerate see the tables.
import app.models  # noqa: F401

config = context.config


def _resolve_url() -> str:
    """Explicit -x argument, then an explicitly configured url, then settings."""
    supplied = (context.get_x_argument(as_dictionary=True) or {}).get("db_url")
    if supplied:
        return supplied
    configured = config.get_main_option("sqlalchemy.url", None)
    # alembic.ini ships with the key present but empty; treat that as unset.
    if configured:
        return configured
    return settings.database_url


DATABASE_URL = _resolve_url()
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """Keep autogenerate from touching anything Alembic did not create."""
    if type_ == "table" and name in {"spatial_ref_sys"}:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
