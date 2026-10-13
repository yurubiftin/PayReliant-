"""Shared test setup. pytest runs this automatically before the tests.

Tests use a SEPARATE database (payreliant_test) so they never touch your
real sandbox data. Each test starts with fresh tables and the sample accounts.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL, TEST_DATABASE_URL
from app.database import Base, get_db
from app.main import app
from app.seed import seed_sample_data


def _create_test_database_if_missing() -> None:
    test_db_name = make_url(TEST_DATABASE_URL).database
    admin_engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": test_db_name}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
    admin_engine.dispose()


_create_test_database_if_missing()
test_engine = create_engine(TEST_DATABASE_URL)
TestSession = sessionmaker(bind=test_engine, autoflush=False)


@pytest.fixture
def db():
    """A fresh database with sample data, for one test."""
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    session = TestSession()
    seed_sample_data(session)
    yield session
    session.close()


@pytest.fixture
def client(db):
    """An API client whose requests use the test database."""

    def _get_test_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_test_db
    yield TestClient(app)
    app.dependency_overrides.clear()
