"""
Test fixtures.

Tests run against TEST_DATABASE_URL (a separate database) so a test run can
never touch development data. The schema is created from the models directly
rather than by running migrations, which keeps the suite fast; a separate test
asserts that migrations and models agree.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app

TEST_URL = settings.test_database_url or settings.database_url.replace("/pgdesk", "/pgdesk_test")

engine = create_engine(TEST_URL, poolclass=None)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    import app.models  # noqa: F401  - registers the tables

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    """A session wrapped in a transaction that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestSession(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
