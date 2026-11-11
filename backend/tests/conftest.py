"""Shared test setup. pytest runs this automatically before the tests.

Tests use a SEPARATE database (payreliant_test) so they never touch your
real sandbox data. Each test starts with fresh tables and the sample accounts.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app import config
from app.config import DATABASE_URL, TEST_DATABASE_URL
from app.database import Base, get_db, get_session_factory
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
test_engine = create_engine(TEST_DATABASE_URL, pool_size=20, max_overflow=20)
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


GATEWAY = {"X-API-Key": config.GATEWAY_API_KEY}


def login(test_client, username, password):
    """Log in and return the Authorization header for that user."""
    r = test_client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def anon_client(db):
    """An API client with NO login and NO API key, using the test database."""

    def _get_test_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_session_factory] = lambda: TestSession
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(anon_client):
    """The default client for most tests: logged in as ADMIN and carrying the gateway API key,
    so it may call every endpoint (like the sandbox operator testing their own system)."""
    anon_client.headers.update(GATEWAY)
    anon_client.headers.update(login(anon_client, "admin", config.ADMIN_PASSWORD))
    return anon_client


@pytest.fixture
def merchant_client(anon_client):
    """A client logged in as the Mama Mboga Grocers merchant (merchant_id 1)."""
    c = TestClient(app)  # its own client, sharing the test-database setup from anon_client
    c.headers.update(login(c, "mamamboga", config.DEMO_MERCHANT_PASSWORD))
    return c
