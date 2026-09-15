# CLAUDE.md

Technical context for Claude Code sessions working in this repo. Keep this file current as the project evolves — update it whenever architecture, conventions, or run commands change. For conceptual/teaching explanations see `LEARNING.md`; for deferred v2+ features see `ROADMAP.md`.

## What this project is

**Doc Digest** — an AI-assisted document processing & learning platform: upload documents (PDFs, chapters, notes), run automated processing (metadata extraction, configurable checks, an AI-generated summary), track status through a workflow, ask multi-turn follow-up questions about a document, and view aggregate metrics on a dashboard. Built as two independently deployable FastAPI microservices plus a Streamlit UI, all backed by Postgres, with summarization/Q&A powered by a **self-hosted open-source LLM via Ollama** (not a paid API — genuinely free, no per-token billing).

## Architecture

```
┌──────────────────┐        ┌───────────────────┐        ┌─────────┐
│   streamlit-app   │──────▶│  document-service   │──────▶│ ollama  │
│  (Streamlit UI)   │        │  (FastAPI, :8001)  │        │ (:11434)│
└──────────────────┘        └───────────────────┘        └─────────┘
        │                              │      ▲
        │                              ▼      │ HTTP (reads document data)
        │                          Postgres    │
        │                    (document-service │
        │                        owns this DB) │
        ▼                                      │
┌───────────────────┐──────────────────────────┘
│  reporting-service │
│  (FastAPI, :8002)  │
└───────────────────┘
```

**Hard rule: the two services are decoupled on purpose.**
- `document-service` owns Postgres exclusively — it's the only service with DB credentials, and the only one that runs Alembic migrations.
- `reporting-service` has **no database access**. It computes all aggregates/metrics by calling `document-service`'s HTTP API (via an `httpx` client) and processing the responses in-memory. This was a deliberate choice over a shared-DB/read-only-role design, to keep a schema change in one service from silently breaking the other. See `LEARNING.md` Phase 3 for the full reasoning.
- `streamlit-app` calls both services over HTTP and renders no business logic of its own beyond display/formatting.

**streamlit-app pages:** `Home.py` (upload a PDF/.txt — this is the sidebar's "Home" entry, and the only place to upload), `pages/1_Documents.py` (list + filter + filename search + per-document detail/metadata/AI summary/download/history timeline, plus a chat interface for asking questions about the selected document), `pages/2_Dashboard.py` (stat tiles + status bar chart + recent activity, from `reporting-service`). Shared HTTP-calling code lives in `streamlit-app/api_client.py`, imported directly by every page (Streamlit puts the project root on `sys.path`). The sidebar label for the entry-point script is exactly its filename (case preserved) — that's why it's named `Home.py`, not `app.py`.

**document-service endpoints:** `POST /api/v1/documents` (upload), `GET /api/v1/documents` (paginated list), `GET /api/v1/documents/{id}`, `GET /api/v1/documents/{id}/history`, `GET /api/v1/documents/{id}/content` (raw file bytes — only `streamlit-app`'s backend calls this directly; the browser never does, see Conventions below), `GET /api/v1/documents/{id}/messages` (chat history), `POST /api/v1/documents/{id}/ask` (ask a question about a COMPLETED document — synchronous, calls Ollama, persists and returns the assistant's reply; 400 if the document hasn't finished processing).

**reporting-service endpoints:** `GET /api/v1/reports/summary` (counts by status), `GET /api/v1/reports/processing-stats` (failure rate + average processing duration), `GET /api/v1/reports/recent-activity?limit=` — all built by paginating `document-service`'s document list, no other endpoint needed. `reporting-service` returns `502` (not a crash) when `document-service` is unreachable.

## AI-assisted learning features

- **Model runtime:** an `ollama` service in `docker-compose.yml` (official `ollama/ollama` image), joining the network the same way Postgres does — `document-service` reaches it at `http://ollama:11434` (overridden locally to `http://localhost:11434` via `.env`, mirroring the Postgres-port pattern below), never the browser. `document-service` depends on it with `condition: service_started` only (not `service_healthy` — ollama has no `pg_isready`-equivalent, and every call into it is designed to degrade gracefully instead of requiring readiness at startup).
- **Model:** **Llama 3.1 8B** (`ollama pull llama3.1`), pulled via `docker compose exec ollama ollama pull llama3.1`. Fallback if generation is too slow: a smaller model (Phi-3.5 mini 3.8B, or Llama 3.2 3B) — just change `OLLAMA_MODEL`.
- **Why Ollama over the Claude API:** genuinely free (no per-token billing, runs locally) — the explicit requirement for this feature. Trade-offs accepted knowingly: slower on CPU, lower quality than a hosted frontier model, no equivalent to Anthropic's server-side prompt caching (repeated context costs latency here, not dollars).
- **No RAG / vector database.** A single uploaded document fits comfortably inside even a local model's context window — full document text goes directly in the prompt (capped at `MAX_WORDS` in `app/services/summarization.py` as a defensive ceiling, not real chunking). RAG (embeddings + a vector store) would only become relevant for *cross-document* search over a large corpus, which is out of scope for now.
- **Known gap: `MAX_WORDS` (12,000 words) doesn't actually reflect what the model sees.** `ollama_client.chat()` doesn't set `num_ctx`, so Ollama silently uses its own default context window (**4,096 tokens**, confirmed via `ollama ps` against the running container) regardless of `MAX_WORDS` — in practice only ~3,000 words (~5–10 pages) of a document are ever visible to the model before content is silently dropped; nothing errors, results just quietly degrade. Not fixed yet — see `ROADMAP.md` for the concrete fix (pass `options.num_ctx` explicitly, ~16384–32768 is the comfortable range on a 16GB laptop) and the RAM math behind that range.
- **Summarization** is a step in `document-service`'s processing pipeline (`app/services/processing.py`), after metadata extraction: `app/services/summarization.py` builds a prompt and calls `app/services/ollama_client.py`, storing the result in `Document.summary` (a new nullable `Text` column — kept separate from the structured `extracted_metadata` JSON rather than folded into it, since a summary is prose, not structured data). **Failure here is non-fatal, unlike the existing checks/extraction**: if Ollama is down, slow, or errors, the document still reaches COMPLETED with `summary = null` and a warning is logged — summarization is an enhancement layer on top of the core workflow, not a gate on it.
- **Conversational Q&A** lives in `document-service` (it already owns the document's full text via `app/services/extraction.py`'s `extract_text` — no reason for a new service to duplicate that access). `app/models/chat_message.py`'s `ChatMessage` table (`document_id`, `role`, `content`, `created_at`) is append-only, same pattern as `ProcessingHistory`. `app/services/chat.py`'s `ask_question` loads prior messages for the document, sends the full conversation + document text (as a system message) to Ollama via `ollama_client.chat`, persists and returns both the user's question and the assistant's reply. Unlike summarization, a failure here propagates (→ 502 via the `OllamaServiceError` handler in `app/main.py`) rather than degrading silently — this is a synchronous, user-initiated call, so the user should see it failed rather than getting nothing back.
- **UI:** the chat interface lives on `pages/1_Documents.py` (not a separate page), using Streamlit's native `st.chat_message`/`st.chat_input` — the only place in this app that uses them, everywhere else uses plain widgets. Gated behind `document["status"] == "COMPLETED"`, matching the backend's 400 rule.

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, Alembic, Pydantic v2, `pydantic-settings`
- **Frontend:** Streamlit, Altair (charts), pandas
- **Database:** PostgreSQL (owned solely by `document-service`)
- **Containerization:** Docker, Docker Compose
- **Testing:** pytest
- **AI:** Ollama (self-hosted open-source LLM, Llama 3.1 8B) for summarization + Q&A — see above

## Repo layout

```
document-workflow-platform/
├── CLAUDE.md
├── LEARNING.md
├── ROADMAP.md
├── README.md
├── docker-compose.yml
├── scripts/
│   └── seed_demo_data.py   # stdlib-only demo-data seeder, no venv needed
├── document-service/
│   ├── README.md
│   ├── app/
│   │   ├── main.py          # exception handlers registered here
│   │   ├── core/             # config, logging.py
│   │   ├── models/           # SQLAlchemy ORM models (incl. chat_message.py)
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── routers/          # FastAPI route handlers
│   │   ├── services/         # business logic: processing pipeline, checks,
│   │   │                     # extraction, ollama_client.py, summarization.py, chat.py
│   │   └── db/                # session/engine setup
│   ├── alembic/
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── reporting-service/
│   ├── README.md
│   ├── app/
│   │   ├── main.py           # exception handlers registered here
│   │   ├── core/              # config, logging.py
│   │   ├── schemas/
│   │   ├── routers/
│   │   ├── services/          # aggregation logic
│   │   └── clients/           # httpx client for document-service
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
└── streamlit-app/
    ├── README.md
    ├── Home.py              # entry point — shows as "Home" in the sidebar, includes upload
    ├── api_client.py        # shared HTTP client, imported by every page
    ├── pages/
    │   ├── 1_Documents.py
    │   └── 2_Dashboard.py
    ├── Dockerfile
    ├── requirements.txt
    └── .env.example
```

## Conventions

- Every service's FastAPI routes are versioned under `/api/v1/...`.
- Every service exposes a `GET /health` endpoint.
- The browser only ever talks to `streamlit-app`. Anything the UI needs from `document-service`/`reporting-service` (including raw file bytes for download) is fetched server-side by `streamlit-app`'s Python code and handed to the browser from there — never a direct link/redirect to another service's port, since inside Docker those are only reachable by internal hostname (`document-service:8001`), not from the user's actual browser.
- ORM models (`models/`) and API schemas (`schemas/`) are always separate — never return an ORM object directly from a route.
- DB sessions are provided via FastAPI `Depends`, never instantiated inside route bodies.
- Config is loaded via `pydantic-settings` from environment variables; each service ships a `.env.example` and gitignores its real `.env`.
- `document-service` is the only service with Alembic migrations; schema changes always go through a migration, never manual DB edits.
- Postgres ENUM columns share one SQLAlchemy `Enum` object (`document_status_enum` in `app/models/document.py`) rather than each column declaring its own — reusing it is what stops Alembic from trying to `CREATE TYPE` the same enum twice. If a *new* migration adds another column using this enum, autogenerate will emit a plain `sa.Enum(...)` for it — **hand-edit that to `sqlalchemy.dialects.postgresql.ENUM(..., create_type=False)`** before applying, or it fails with "type already exists" (generic `sa.Enum(..., create_type=False)` does not reliably prevent this — confirmed by testing in Phase 2; see LEARNING.md). Not every new column needs this: `ChatMessage.role` is a plain `String(20)`, not a Postgres enum, since it's a small fixed set (`"user"`/`"assistant"`) that doesn't warrant the reuse machinery above.
- Commit style: small, phase-scoped commits (see project phases below).
- Every service has a `.dockerignore` (excludes `.venv/`, `__pycache__/`, `.env`, tests) — without it, a Dockerfile's `COPY . .` sweeps up the local venv into the build context (hit this for real in Phase 4: `streamlit-app`'s context was 142MB until its `.dockerignore` was added).
- Every Dockerfile is multi-stage (`builder` installs deps with `pip install --user`, the runtime stage only copies the installed packages + app code) and every container runs as a non-root `appuser` (created via `useradd --create-home --uid 1000`, with `PATH` pointing at `~/.local/bin`). `document-service`'s Dockerfile also pre-creates and `chown`s the `storage/` dir *before* the named volume is ever mounted there — that's what lets the non-root user write to it (see the note below about a stale volume if this ever needs re-diagnosing).
- Both FastAPI services configure logging once at import time (`app/core/logging.py` → `configure_logging()`, called at the top of `main.py`) and register two exception handlers there: one for each service's own "upstream failed" exception (`reporting-service`'s `DocumentServiceError` → 502, `document-service`'s `OllamaServiceError` → 502) and a catch-all `@app.exception_handler(Exception)` → 500 with a logged traceback and a safe, consistent `{"detail": "..."}` JSON body. Without the catch-all, an unexpected error returns Starlette's bare plain-text 500 with nothing logged — this happened for real during the Phase 5 permission bug, which is what motivated adding it. Routes deliberately don't `try/except` these upstream-error types per-route — each is handled once, centrally. (`OllamaServiceError` only ever reaches this handler via the synchronous `/ask` endpoint — the background summarization step in `app/services/processing.py` catches it itself and degrades to no summary instead of letting it propagate.)
- Testing an app's exception handlers with FastAPI's `TestClient`: the default (`raise_server_exceptions=True`) re-raises exceptions caught by a **catch-all `Exception` handler** straight into the test, even though the handler produced a valid response — by design, so tests fail loudly on real bugs. A handler registered for a *specific* exception type (like `DocumentServiceError`) doesn't trigger this. To actually test the catch-all handler's behavior, construct a dedicated `TestClient(app, raise_server_exceptions=False)` for that one test (see `test_unhandled_exception_returns_json_not_plain_text` in both services).

## Project phases (status)

- [x] Phase 0 — repo, environment & skeleton
- [x] Phase 1 — document-service: data model + upload API
- [x] Phase 2 — document-service: async processing workflow
- [x] Phase 3 — reporting-service: HTTP-only aggregation API
- [x] Phase 4 — Streamlit UI
- [x] Phase 5 — containerize everything
- [x] Phase 6 — polish v1
- [x] Phase 7 — AI-assisted learning: Ollama-backed summarization + multi-turn Q&A

## How to run

Local dev (each service has its own venv) and Docker Compose instructions are in `README.md`.

Verified via `docker compose up --build`: all four containers (`postgres`, `document-service`, `reporting-service`, `streamlit-app`) build and start cleanly; `postgres` reports healthy; `document-service` runs `alembic upgrade head` on container start, then serves; upload/list/get/history all confirmed working against the containerized Postgres, including the full UPLOADED→PROCESSING→COMPLETED/FAILED pipeline. `reporting-service`'s three report endpoints confirmed working against real data, including reaching `document-service` over the Compose network (`document-service:8001`) — and confirmed returning a clean `502` (not a crash) when `document-service` is unreachable. Also verified standalone (local venvs, no Docker).

`streamlit-app` verified in a real headless-Chromium browser (Playwright), not just HTTP status checks: every page screenshotted, an actual file uploaded through the UI end-to-end (browser → `document-service` → Postgres → response rendered), a document selected and its processing-history timeline confirmed rendering, and the dashboard's stat tiles + status-colored bar chart confirmed against real aggregate data. Zero browser console errors across all of it.

Multi-stage + non-root images (Phase 5) confirmed working end-to-end: rebuilt all three, confirmed `whoami` is `appuser` (not root) in every container, confirmed a real upload/process/report/download cycle still works. Image sizes: `document-service` 296MB, `reporting-service` 246MB, `streamlit-app` 790MB (large mainly because of pandas/numpy/pyarrow for the dashboard's charts — none of our dependencies need a C compiler, so the multi-stage split's main win here is the non-root security posture and a clean install/run separation, not a dramatic size cut; that trade-off would look different for a service with compiled dependencies).

Phase 6 (polish) verified: `python scripts/seed_demo_data.py` run against a freshly rebuilt stack — 5 sample documents uploaded, 3 completed with correct extracted metadata, 2 failed for the expected reasons (bad extension, empty file), confirming both branches of the processing workflow from a clean checkout. Logging confirmed showing up in `document-service`'s container logs with the expected format and content. Both exception handlers (per-service `Exception` catch-all, plus `reporting-service`'s `DocumentServiceError` → 502) verified with dedicated tests, not just inline reasoning — 25 backend tests total (15 `document-service`, 10 `reporting-service`), all passing, plus a full browser regression pass with zero non-Streamlit console errors.

Phase 7 (Ollama-backed summarization + Q&A) verified end-to-end, twice — once locally (`uvicorn` against a Compose-managed Ollama on `localhost:11434`) and once fully containerized (`docker compose up --build`, all 5 containers incl. `ollama`, `document-service` reaching it at `http://ollama:11434`): uploaded a real text document, confirmed the background pipeline produced a correctly-formatted `summary` (headline + key points) via a real `llama3.1` call, asked a multi-turn Q&A conversation (`/ask` × 2) and confirmed the second answer correctly resolved a pronoun ("that") back to context from the first answer — proving conversation replay actually works, not just that an endpoint returns 200. Failure mode confirmed by stopping the `ollama` container mid-session: a new upload still reached `COMPLETED` with `summary: null` and a logged warning (traceback included) instead of failing the document, and `/ask` against it returned a clean `502` with a real error message instead of a crash. `document-service`'s test suite (23 tests, up from 15) mocks Ollama by default (`conftest.py`'s `mock_summarization` fixture) so it runs in under a second instead of making real network calls. The Streamlit UI was verified in a real headless-Chromium browser (Playwright): the AI-summary panel and the `st.chat_message` conversation (including prior turns from a completely fresh page load, i.e. real persistence, not client-side state) both rendered correctly, with the rebrand (`Doc Digest` in every page title) confirmed too.

Two environment quirks on this dev machine, both already fixed in the repo — flagging in case they resurface after a machine change or reinstall:
- Docker Desktop's bin directory (`%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin`) isn't on PATH by default — add it to PATH (or open a fresh terminal after install) before running `docker` commands, otherwise `docker-credential-desktop` fails to resolve.
- This machine has a **native PostgreSQL install already bound to port 5432** on the host. `docker-compose.yml` maps the `postgres` container to host port **5433** instead (its internal container port is still 5432, so other containers reach it at `postgres:5432` unaffected) — `document-service/.env(.example)` points `DATABASE_URL` at `localhost:5433` for local (non-Docker) runs accordingly. If a future machine doesn't have a conflicting local Postgres, this remapping is unnecessary but harmless.
- If `document-service` ever starts returning 500s on upload again after a Dockerfile/user change: check `docker compose exec document-service ls -la /app/storage`. A **named volume created before `document-service` switched to running as non-root** keeps its old root ownership across rebuilds — only a brand-new volume inherits the image's `appuser`-owned directory. Fix: `docker compose down`, `docker volume rm document-workflow-platform_document-files`, `docker compose up` (loses locally-stored uploaded files, not the Postgres data/metadata — only do this if those files are disposable, e.g. local dev test data).

## Local dev database workflow

For fast iteration on `document-service` without rebuilding a Docker image each time:
```
docker compose up -d postgres        # just the DB, mapped to localhost:5433
cd document-service
.venv\Scripts\activate
alembic upgrade head                 # apply any new/pending migrations
uvicorn app.main:app --reload --port 8001
```
After changing a model in `app/models/`, generate a new migration with `alembic revision --autogenerate -m "..."`, read the generated file before applying (autogenerate isn't always right), then `alembic upgrade head`.
