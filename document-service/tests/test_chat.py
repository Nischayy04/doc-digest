import io

from fastapi import status


def _upload_completed_document(client, filename="notes.txt", content=b"hello world"):
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    return response.json()["id"]


def test_ask_on_completed_document_returns_assistant_reply(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.chat.ollama_client.chat", lambda messages: "The document is about testing."
    )
    document_id = _upload_completed_document(client)

    response = client.post(
        f"/api/v1/documents/{document_id}/ask", json={"question": "What is this about?"}
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"] == "The document is about testing."
    assert body["document_id"] == document_id


def test_ask_persists_both_turns_in_message_history(client, monkeypatch):
    monkeypatch.setattr("app.services.chat.ollama_client.chat", lambda messages: "An answer.")
    document_id = _upload_completed_document(client)

    client.post(f"/api/v1/documents/{document_id}/ask", json={"question": "A question?"})

    messages = client.get(f"/api/v1/documents/{document_id}/messages").json()

    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "A question?"),
        ("assistant", "An answer."),
    ]


def test_ask_on_document_not_yet_completed_returns_400(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("script.exe", io.BytesIO(b"binary"), "application/octet-stream")},
    )
    document_id = response.json()["id"]  # processing fails -> status FAILED, not COMPLETED

    response = client.post(
        f"/api/v1/documents/{document_id}/ask", json={"question": "What is this?"}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_ask_for_missing_document_returns_404(client):
    response = client.post(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000/ask",
        json={"question": "Hello?"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_ask_when_ollama_unreachable_returns_502(client, monkeypatch):
    from app.services.ollama_client import OllamaServiceError

    def broken_chat(messages):
        raise OllamaServiceError("Failed to reach Ollama: connection refused")

    monkeypatch.setattr("app.services.chat.ollama_client.chat", broken_chat)
    document_id = _upload_completed_document(client)

    # Needs its own TestClient with raise_server_exceptions=False, same
    # reasoning as test_unhandled_exception_returns_json_not_plain_text in
    # test_documents.py: a handler registered for a specific exception type
    # (OllamaServiceError, not the catch-all Exception) doesn't trigger the
    # shared client fixture's re-raise, so this isn't strictly required here
    # — but kept for consistency and to assert the real JSON body a client
    # receives.
    from fastapi.testclient import TestClient

    from app.main import app

    # `app` is the same module-level singleton the `client` fixture already
    # applied its get_db override to, so that override is still active here.
    with TestClient(app, raise_server_exceptions=False) as non_raising_client:
        response = non_raising_client.post(
            f"/api/v1/documents/{document_id}/ask", json={"question": "What is this?"}
        )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert "detail" in response.json()


def test_messages_for_missing_document_returns_404(client):
    response = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000/messages")

    assert response.status_code == status.HTTP_404_NOT_FOUND
