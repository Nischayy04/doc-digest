"""Thin HTTP client shared by every page. Streamlit's multipage app adds the
project root (where Home.py lives) to sys.path, so `pages/*.py` can import
this module directly with `from api_client import ...` — no package needed.
"""

import os
from typing import Any

import requests

DOCUMENT_SERVICE_URL = os.environ.get("DOCUMENT_SERVICE_URL", "http://localhost:8001")
REPORTING_SERVICE_URL = os.environ.get("REPORTING_SERVICE_URL", "http://localhost:8002")

TIMEOUT_SECONDS = 10


class ApiError(Exception):
    """Raised for anything that goes wrong calling document-service or
    reporting-service — a page catches this and shows st.error(...)."""


def _error_message(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return response.text or f"HTTP {response.status_code}"


def _get(base_url: str, path: str, params: dict | None = None) -> Any:
    try:
        response = requests.get(f"{base_url}{path}", params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach {base_url}: {exc}") from exc
    if not response.ok:
        raise ApiError(_error_message(response))
    return response.json()


def upload_document(filename: str, content: bytes, content_type: str) -> dict:
    try:
        response = requests.post(
            f"{DOCUMENT_SERVICE_URL}/api/v1/documents",
            files={"file": (filename, content, content_type)},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach document-service: {exc}") from exc
    if not response.ok:
        raise ApiError(_error_message(response))
    return response.json()


def list_documents(skip: int = 0, limit: int = 100) -> list[dict]:
    return _get(DOCUMENT_SERVICE_URL, "/api/v1/documents", params={"skip": skip, "limit": limit})


def get_document(document_id: str) -> dict:
    return _get(DOCUMENT_SERVICE_URL, f"/api/v1/documents/{document_id}")


def get_document_history(document_id: str) -> list[dict]:
    return _get(DOCUMENT_SERVICE_URL, f"/api/v1/documents/{document_id}/history")


def get_document_content(document_id: str) -> tuple[bytes, str]:
    """Fetches the raw file bytes server-side so the browser never has to
    reach document-service directly — only streamlit-app talks to the
    backend services, the browser only ever talks to streamlit-app.
    Returns (content_bytes, content_type)."""
    try:
        response = requests.get(
            f"{DOCUMENT_SERVICE_URL}/api/v1/documents/{document_id}/content",
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach document-service: {exc}") from exc
    if not response.ok:
        raise ApiError(_error_message(response))
    return response.content, response.headers.get("content-type", "application/octet-stream")


def get_summary_report() -> dict:
    return _get(REPORTING_SERVICE_URL, "/api/v1/reports/summary")


def get_processing_stats_report() -> dict:
    return _get(REPORTING_SERVICE_URL, "/api/v1/reports/processing-stats")


def get_recent_activity_report(limit: int = 10) -> dict:
    return _get(REPORTING_SERVICE_URL, "/api/v1/reports/recent-activity", params={"limit": limit})
