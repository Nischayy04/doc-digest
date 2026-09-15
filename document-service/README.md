# document-service

FastAPI service that owns document upload, storage, and the async processing workflow (validation checks, metadata extraction, and an AI-generated summary via a self-hosted Ollama model). Also owns document Q&A — multi-turn conversational chat grounded in a document's text, also via Ollama. The **only** service with database access in this system — see the root [README](../README.md) and [CLAUDE.md](../CLAUDE.md) for the full architecture.

## Endpoints (under `/api/v1`)

| Method | Path | Description |
|---|---|---|
| POST | `/documents` | Upload a PDF or `.txt` file. Kicks off background processing. |
| GET | `/documents` | Paginated list (`skip`, `limit` query params). |
| GET | `/documents/{id}` | One document's current status, extracted metadata, and AI summary. |
| GET | `/documents/{id}/content` | The original uploaded file's bytes. |
| GET | `/documents/{id}/history` | Every status transition, in order, with a timestamp and message. |
| GET | `/documents/{id}/messages` | The document's Q&A chat history, in order. |
| POST | `/documents/{id}/ask` | Ask a question about the document (must be `COMPLETED`); calls Ollama synchronously, persists and returns the assistant's reply. `400` if not yet completed, `502` if Ollama is unreachable. |
| GET | `/health` | Liveness check. |

Interactive docs at `/docs` once running.

Summarization and Q&A require the `ollama` service (see root `docker-compose.yml`) with the `llama3.1` model pulled — see `CLAUDE.md`'s "AI-assisted learning features" section. Summarization failures are non-fatal (the document still completes, just without a summary); a failed `/ask` call returns a clean `502` instead.

## Run locally (without Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # then edit DATABASE_URL if needed
alembic upgrade head            # apply migrations (Postgres must be reachable)
uvicorn app.main:app --reload --port 8001
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DEBUG` | `false` | `true` sets log level to DEBUG. |
| `DATABASE_URL` | — | SQLAlchemy connection string for Postgres. |
| `STORAGE_DIR` | `./storage` | Where uploaded files are saved on disk. |
| `MAX_UPLOAD_SIZE_BYTES` | `20971520` (20MB) | Upload size limit, enforced while streaming. |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Base URL for the Ollama API. Use `http://localhost:11434` for local (non-Docker) runs against a Compose-managed Ollama. |
| `OLLAMA_MODEL` | `llama3.1` | Model name, as pulled via `ollama pull`. |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Request timeout for Ollama calls — local CPU generation is slow. |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests run against an in-memory SQLite database (fast, no Postgres needed) — see `tests/conftest.py` and `LEARNING.md` Phase 1 for why that trade-off is fine here.

## Database migrations

This is the only service with Alembic migrations. After changing a model in `app/models/`:

```bash
alembic revision --autogenerate -m "describe the change"
# read the generated file in alembic/versions/ before applying — autogenerate isn't always right
alembic upgrade head
```

See `CLAUDE.md`'s Conventions section for a gotcha specific to adding new columns that use the `document_status` Postgres enum.
