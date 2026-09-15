import httpx

from app.core.config import settings


class OllamaServiceError(Exception):
    """Raised when the self-hosted Ollama model can't be reached, times out,
    or returns an error. Mirrors reporting-service's DocumentServiceError —
    this service is fine, its (local) upstream is what failed."""


def chat(messages: list[dict]) -> str:
    """Sends a full message list (system/user/assistant turns) to Ollama's
    chat API and returns the assistant's reply text. Synchronous, matching
    the rest of document-service's route/service layer — callers here are
    either a background task (summarization) or a synchronous request
    handler (Q&A), neither of which is in an async context."""
    try:
        response = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={"model": settings.ollama_model, "messages": messages, "stream": False},
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OllamaServiceError(f"Failed to reach Ollama: {exc}") from exc
    return response.json()["message"]["content"]
