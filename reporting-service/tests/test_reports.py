import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.clients.document_service import DocumentServiceError
from app.main import app
from app.routers.reports import get_document_service_client


def _doc(filename: str, status: str, created_at: datetime, updated_at: datetime) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "filename": filename,
        "status": status,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }


def test_summary_counts_documents_by_status(client, fake_client):
    now = datetime.now(timezone.utc)
    fake_client.documents = [
        _doc("a.txt", "UPLOADED", now, now),
        _doc("b.txt", "COMPLETED", now, now),
        _doc("c.txt", "COMPLETED", now, now),
        _doc("d.txt", "FAILED", now, now),
    ]

    response = client.get("/api/v1/reports/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 4
    assert body["counts_by_status"] == {
        "UPLOADED": 1,
        "PROCESSING": 0,
        "COMPLETED": 2,
        "FAILED": 1,
    }


def test_processing_stats_computes_failure_rate_and_average_duration(client, fake_client):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fake_client.documents = [
        _doc("a.txt", "COMPLETED", base, base + timedelta(seconds=10)),
        _doc("b.txt", "COMPLETED", base, base + timedelta(seconds=30)),
        _doc("c.txt", "FAILED", base, base + timedelta(seconds=5)),
        _doc("d.txt", "UPLOADED", base, base),  # still in flight, excluded
    ]

    response = client.get("/api/v1/reports/processing-stats")

    assert response.status_code == 200
    body = response.json()
    assert body["completed_count"] == 2
    assert body["failed_count"] == 1
    assert body["failure_rate"] == pytest.approx(1 / 3)
    assert body["average_processing_seconds"] == pytest.approx(15.0)  # (10+30+5)/3


def test_processing_stats_with_no_finished_documents(client, fake_client):
    fake_client.documents = []

    response = client.get("/api/v1/reports/processing-stats")

    body = response.json()
    assert body["completed_count"] == 0
    assert body["failed_count"] == 0
    assert body["failure_rate"] == 0.0
    assert body["average_processing_seconds"] is None


def test_recent_activity_sorted_by_updated_at_desc_and_limited(client, fake_client):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fake_client.documents = [
        _doc(f"{i}.txt", "COMPLETED", base, base + timedelta(minutes=i)) for i in range(1, 6)
    ]

    response = client.get("/api/v1/reports/recent-activity", params={"limit": 3})

    assert response.status_code == 200
    filenames = [item["filename"] for item in response.json()["items"]]
    assert filenames == ["5.txt", "4.txt", "3.txt"]


def test_recent_activity_rejects_limit_out_of_range(client):
    response = client.get("/api/v1/reports/recent-activity", params={"limit": 0})

    assert response.status_code == 422


def test_summary_returns_502_when_document_service_unreachable():
    class FailingClient:
        async def fetch_all_documents(self) -> list[dict]:
            raise DocumentServiceError("document-service is unreachable")

    app.dependency_overrides[get_document_service_client] = FailingClient
    try:
        from fastapi.testclient import TestClient

        with TestClient(app) as test_client:
            response = test_client.get("/api/v1/reports/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "document-service is unreachable" in response.json()["detail"]


def test_unhandled_exception_returns_json_not_plain_text():
    # Same idea as document-service's equivalent test: a truly unexpected
    # bug (not DocumentServiceError, which already has its own handler)
    # should come back as clean JSON, not a bare plain-text 500. Needs
    # raise_server_exceptions=False for the same reason as there — a
    # catch-all Exception handler is treated differently by TestClient's
    # default than a handler registered for a specific exception type.
    from fastapi.testclient import TestClient

    class BrokenClient:
        async def fetch_all_documents(self) -> list[dict]:
            raise RuntimeError("simulated unexpected failure")

    app.dependency_overrides[get_document_service_client] = BrokenClient
    try:
        with TestClient(app, raise_server_exceptions=False) as non_raising_client:
            response = non_raising_client.get("/api/v1/reports/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
