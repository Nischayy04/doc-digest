# reporting-service

FastAPI service that computes aggregate metrics over documents. Has **no database of its own** — everything is computed by calling `document-service`'s API and aggregating the response in memory. See the root [README](../README.md) and [CLAUDE.md](../CLAUDE.md) for why the two services are deliberately decoupled this way.

## Endpoints (under `/api/v1`)

| Method | Path | Description |
|---|---|---|
| GET | `/reports/summary` | Total document count + counts by status. |
| GET | `/reports/processing-stats` | Failure rate and average processing duration (only counts documents that have finished). |
| GET | `/reports/recent-activity` | Most recently updated documents (`limit` query param, default 10). |
| GET | `/health` | Liveness check. |

Interactive docs at `/docs` once running. If `document-service` is unreachable, every report endpoint returns `502` with a message — not a crash, and not a silent empty report.

## Run locally (without Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # point DOCUMENT_SERVICE_URL at a running document-service
uvicorn app.main:app --reload --port 8002
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DEBUG` | `false` | `true` sets log level to DEBUG. |
| `DOCUMENT_SERVICE_URL` | `http://localhost:8001` | Base URL of `document-service`. Inside Docker Compose this is the internal hostname `http://document-service:8001`, not a browser-reachable address. |
| `DOCUMENT_SERVICE_TIMEOUT_SECONDS` | `10.0` | HTTP timeout for calls to `document-service`. |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Two layers: `test_reports.py` exercises the routes with a fake `DocumentServiceClient` (via FastAPI dependency override, no network); `test_document_service_client.py` tests the real HTTP client's pagination/error handling against `httpx.MockTransport` (no server needed either).
