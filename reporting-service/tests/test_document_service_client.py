import httpx
import pytest

from app.clients.document_service import DocumentServiceClient, DocumentServiceError

pytestmark = pytest.mark.anyio


async def test_fetch_all_documents_pages_until_a_short_page():
    all_documents = [{"id": str(i), "filename": f"{i}.txt"} for i in range(250)]
    requested_skips = []

    def handler(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params.get("skip", 0))
        limit = int(request.url.params.get("limit", 100))
        requested_skips.append(skip)
        return httpx.Response(200, json=all_documents[skip : skip + limit])

    client = DocumentServiceClient(
        base_url="http://document-service", transport=httpx.MockTransport(handler)
    )

    documents = await client.fetch_all_documents()

    assert len(documents) == 250
    # 100 + 100 + 50 -> three pages, the last one short, which is what
    # signals fetch_all_documents to stop.
    assert requested_skips == [0, 100, 200]


async def test_fetch_all_documents_handles_a_single_empty_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = DocumentServiceClient(
        base_url="http://document-service", transport=httpx.MockTransport(handler)
    )

    documents = await client.fetch_all_documents()

    assert documents == []


async def test_fetch_all_documents_raises_document_service_error_on_http_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = DocumentServiceClient(
        base_url="http://document-service", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(DocumentServiceError):
        await client.fetch_all_documents()
