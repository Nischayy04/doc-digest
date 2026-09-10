import httpx

from app.core.config import settings


class DocumentServiceError(Exception):
    """Raised when document-service can't be reached or returns an error.

    This is the one failure mode that matters here: since reporting-service
    has no database of its own, document-service being down means
    reporting-service genuinely cannot produce a report — there's no local
    fallback data to serve instead.
    """


class DocumentServiceClient:
    """The only coupling point between the two services: an HTTP client
    against document-service's public API. No shared database, no shared
    Python code — just this contract. See LEARNING.md Phase 3.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url or settings.document_service_url
        self.timeout = timeout if timeout is not None else settings.document_service_timeout_seconds
        # transport is only ever set in tests, to swap in httpx.MockTransport
        # instead of making a real network call.
        self.transport = transport

    async def fetch_all_documents(self) -> list[dict]:
        """Pages through document-service's document list until a
        short/empty page signals the end. Returns raw dicts — callers
        validate/parse into whatever schema they need."""
        documents: list[dict] = []
        skip = 0
        limit = 100
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout, transport=self.transport
            ) as client:
                while True:
                    response = await client.get(
                        "/api/v1/documents", params={"skip": skip, "limit": limit}
                    )
                    response.raise_for_status()
                    page = response.json()
                    documents.extend(page)
                    if len(page) < limit:
                        break
                    skip += limit
        except httpx.HTTPError as exc:
            raise DocumentServiceError(
                f"Failed to fetch documents from document-service: {exc}"
            ) from exc
        return documents
