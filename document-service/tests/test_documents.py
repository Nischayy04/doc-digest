import io

from fastapi import status

from app.core.config import settings


def _upload(client, filename="sample.txt", content=b"hello world", content_type="text/plain"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def test_upload_document_returns_created_document(client):
    response = _upload(client)

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["filename"] == "sample.txt"
    assert body["content_type"] == "text/plain"
    assert body["file_size"] == len(b"hello world")
    assert body["status"] == "UPLOADED"
    assert "id" in body


def test_upload_without_filename_is_rejected(client):
    # FastAPI/Starlette's own multipart parsing rejects a file part with no
    # filename before our route handler ever runs — this asserts that
    # framework-level behavior, not custom validation of ours.
    response = client.post(
        "/api/v1/documents",
        files={"file": ("", io.BytesIO(b"data"), "text/plain")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_upload_over_size_limit_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 5)

    response = _upload(client, content=b"this is definitely more than five bytes")

    assert response.status_code == 413


def test_list_documents_returns_uploaded_documents(client):
    _upload(client, filename="a.txt")
    _upload(client, filename="b.txt")

    response = client.get("/api/v1/documents")

    assert response.status_code == status.HTTP_200_OK
    filenames = {doc["filename"] for doc in response.json()}
    assert filenames == {"a.txt", "b.txt"}


def test_get_document_by_id(client):
    created = _upload(client).json()

    response = client.get(f"/api/v1/documents/{created['id']}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == created["id"]


def test_get_document_not_found_returns_404(client):
    response = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_document_content_returns_the_uploaded_bytes(client):
    original = b"the quick brown fox"
    created = _upload(client, filename="fox.txt", content=original).json()

    response = client.get(f"/api/v1/documents/{created['id']}/content")

    assert response.status_code == status.HTTP_200_OK
    assert response.content == original
    assert response.headers["content-type"].startswith("text/plain")
    assert "fox.txt" in response.headers["content-disposition"]


def test_get_document_content_not_found_returns_404(client):
    response = client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000/content"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_unhandled_exception_returns_json_not_plain_text(client, monkeypatch):
    # An actual bug hit this exact scenario during Phase 5 (a storage
    # permission error raised from inside a route) before the global
    # handler existed: Starlette's default is a bare plain-text
    # "Internal Server Error" with nothing logged. This asserts the
    # handler in app/main.py converts any unhandled exception raised
    # while handling a request into the same JSON shape as our other
    # errors, instead.
    #
    # Needs its own TestClient with raise_server_exceptions=False: the
    # shared `client` fixture re-raises any exception that reaches a 500
    # straight into the test (even one our handler already caught and
    # converted to a response) — useful by default so tests fail loudly on
    # real bugs, but exactly the behavior this test needs to see past to
    # check what a real client actually receives.
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.main import app

    def broken_query(self, *args, **kwargs):
        raise RuntimeError("simulated unexpected failure")

    monkeypatch.setattr(Session, "query", broken_query)

    with TestClient(app, raise_server_exceptions=False) as non_raising_client:
        response = non_raising_client.get("/api/v1/documents")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
