"""
Migrations must produce exactly what the models describe.

The rest of the suite builds its schema with `Base.metadata.create_all`, which
is fast but means the migrations are never exercised. Production only ever gets
its schema from Alembic, so without this file a migration could be forgotten
entirely and every other test would still pass - right up until a deploy fails
on a missing column.

This builds a scratch database, runs `alembic upgrade head` from empty, and
compares the result against the model metadata table by table and column by
column. It also checks the chain has a single head, because two heads is the
failure mode that silently skips half your migrations.
"""
import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.database import Base
from tests.conftest import TEST_URL

#: Sacrificial database, dropped and recreated for this module alone so a failed
#: run can never leave a half-migrated schema behind for the next one.
SCRATCH = f"pgguru_mig_{uuid.uuid4().hex[:8]}"


def _admin_engine():
    """Connects to `postgres` so the scratch database can be created/dropped."""
    base = TEST_URL.rsplit("/", 1)[0]
    return create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="module")
def migrated_engine():
    admin = _admin_engine()
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH}"'))
            conn.execute(text(f'CREATE DATABASE "{SCRATCH}"'))
    except Exception as exc:                                # pragma: no cover
        pytest.skip(f"cannot create a scratch database: {exc}")

    url = f"{TEST_URL.rsplit('/', 1)[0]}/{SCRATCH}"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    # env.py reads the setting, not the config, so point it at the scratch db too.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with admin.connect() as conn:
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :d"), {"d": SCRATCH})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH}"'))


def test_migration_chain_has_a_single_head():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"expected one head, found {heads}"


def test_migrations_run_from_an_empty_database(migrated_engine):
    tables = set(inspect(migrated_engine).get_table_names())
    assert "alembic_version" in tables
    assert len(tables) > 1


def test_migrated_tables_match_the_models(migrated_engine):
    import app.models  # noqa: F401  - registers every table

    migrated = set(inspect(migrated_engine).get_table_names()) - {"alembic_version"}
    declared = set(Base.metadata.tables)

    assert not declared - migrated, (
        f"models declare tables no migration creates: {sorted(declared - migrated)}")
    assert not migrated - declared, (
        f"migrations create tables no model declares: {sorted(migrated - declared)}")


def test_migrated_columns_match_the_models(migrated_engine):
    import app.models  # noqa: F401

    inspector = inspect(migrated_engine)
    problems = []

    for name in sorted(Base.metadata.tables):
        declared = {c.name: c for c in Base.metadata.tables[name].columns}
        actual = {c["name"]: c for c in inspector.get_columns(name)}

        for missing in sorted(set(declared) - set(actual)):
            problems.append(f"{name}.{missing}: in the model, not in the migration")
        for extra in sorted(set(actual) - set(declared)):
            problems.append(f"{name}.{extra}: in the migration, not in the model")
        for shared in sorted(set(declared) & set(actual)):
            if declared[shared].nullable != actual[shared]["nullable"]:
                problems.append(
                    f"{name}.{shared}: nullable differs "
                    f"(model={declared[shared].nullable}, db={actual[shared]['nullable']})")

            # A NOT NULL column whose value comes from a server default in the
            # model but not in the migration passes every other check here and
            # then fails on the first INSERT in production. This caught exactly
            # that on `login_attempts.created_at`.
            model_default = declared[shared].server_default
            db_default = actual[shared].get("default")
            if model_default is not None and db_default is None:
                problems.append(
                    f"{name}.{shared}: the model has a server default, the "
                    f"migration does not - inserts will fail on a migrated database")

    assert not problems, "model/migration drift:\n  " + "\n  ".join(problems)
