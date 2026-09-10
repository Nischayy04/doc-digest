from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.reports import get_document_service_client


class FakeDocumentServiceClient:
    """Stands in for DocumentServiceClient in endpoint tests — no network
    call, just whatever document list the test sets on `.documents`."""

    def __init__(self) -> None:
        self.documents: list[dict] = []

    async def fetch_all_documents(self) -> list[dict]:
        return self.documents


@pytest.fixture()
def fake_client() -> FakeDocumentServiceClient:
    return FakeDocumentServiceClient()


@pytest.fixture()
def client(fake_client: FakeDocumentServiceClient) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_document_service_client] = lambda: fake_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"
