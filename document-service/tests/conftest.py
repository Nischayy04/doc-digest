from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app


@pytest.fixture()
def db_engine() -> Generator:
    """A fresh in-memory SQLite DB per test — fast, and isolated from
    whatever real Postgres instance is configured. See LEARNING.md Phase 1
    for why SQLite is fine here even though production uses Postgres."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_engine, tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db() -> Generator:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # process_document runs as a background task, outside any request, so it
    # can't use the get_db dependency override above — it opens its own
    # session via SessionLocal (imported directly in app.services.processing).
    # Patch that specific reference so background-task writes land in the
    # same test database instead of whatever real DB is configured.
    monkeypatch.setattr("app.services.processing.SessionLocal", testing_session_local)

    # Route uploaded test files to a throwaway per-test directory instead of
    # the real storage dir.
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
