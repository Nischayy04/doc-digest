import io

from fastapi import status

from tests.pdf_fixture import build_minimal_pdf_bytes

# Background tasks scheduled via BackgroundTasks run synchronously within
# TestClient's request/response cycle, so by the time client.post() returns,
# processing has already completed — no polling needed in these tests.


def test_uploading_a_text_file_completes_and_extracts_word_count(client):
    content = b"one two three four five"
    response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", io.BytesIO(content), "text/plain")},
    )
    document_id = response.json()["id"]

    document = client.get(f"/api/v1/documents/{document_id}").json()

    assert document["status"] == "COMPLETED"
    assert document["extracted_metadata"] == {"word_count": 5}


def test_uploading_a_pdf_completes_and_extracts_page_count(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("report.pdf", io.BytesIO(build_minimal_pdf_bytes()), "application/pdf")},
    )
    document_id = response.json()["id"]

    document = client.get(f"/api/v1/documents/{document_id}").json()

    assert document["status"] == "COMPLETED"
    assert document["extracted_metadata"] == {"page_count": 1}


def test_uploading_a_disallowed_extension_fails_processing(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("script.exe", io.BytesIO(b"binary-ish content"), "application/octet-stream")},
    )
    document_id = response.json()["id"]

    document = client.get(f"/api/v1/documents/{document_id}").json()

    assert document["status"] == "FAILED"
    assert document["extracted_metadata"] is None


def test_uploading_an_empty_file_fails_processing(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    document_id = response.json()["id"]

    document = client.get(f"/api/v1/documents/{document_id}").json()

    assert document["status"] == "FAILED"


def test_history_records_every_transition_in_order(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    document_id = response.json()["id"]

    history = client.get(f"/api/v1/documents/{document_id}/history").json()

    transitions = [(entry["from_status"], entry["to_status"]) for entry in history]
    assert transitions == [
        ("UPLOADED", "PROCESSING"),
        ("PROCESSING", "COMPLETED"),
    ]
    # created_at should be non-decreasing in the order returned
    timestamps = [entry["created_at"] for entry in history]
    assert timestamps == sorted(timestamps)


def test_history_for_missing_document_returns_404(client):
    response = client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000/history"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
