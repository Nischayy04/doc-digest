# Doc Digest

An AI-assisted document processing & learning platform: upload documents (PDFs, chapters, notes), run automated processing (metadata extraction, configurable checks, an AI-generated summary), track workflow status, ask multi-turn follow-up questions about a document, and view aggregate metrics on a dashboard.

Two independently deployable FastAPI microservices ([`document-service`](./document-service/README.md), [`reporting-service`](./reporting-service/README.md)) plus a [Streamlit UI](./streamlit-app/README.md), backed by PostgreSQL, with summarization/Q&A powered by a self-hosted open-source LLM via [Ollama](https://ollama.com) (Llama 3.1 8B) — no per-token API billing. Each service's own README has endpoint tables, local-run instructions, and its `.env` variables — this file covers running the whole stack together.

- **Architecture, conventions, repo layout:** see [`CLAUDE.md`](./CLAUDE.md)
- **Concept-by-concept explanations as the project is built:** see [`LEARNING.md`](./LEARNING.md)
- **Deferred v2+ upgrades and why:** see [`ROADMAP.md`](./ROADMAP.md)

## Status

Phases 0–7 done — the full pipeline (upload → async processing incl. AI summary → tracking → reporting → UI), containerized with multi-stage non-root Docker images, plus Ollama-backed document Q&A. See `CLAUDE.md`'s "Project phases" section for the detailed checklist.

## Quick start (Docker Compose)

```bash
docker compose up --build
docker compose exec ollama ollama pull llama3.1   # first run only — ~4.7GB download
```

- Streamlit UI → http://localhost:8501
- `document-service` → http://localhost:8001/docs
- `reporting-service` → http://localhost:8002/docs
- `ollama` → http://localhost:11434

Summarization and the document Q&A chat won't work until the model is pulled; the rest of the app works immediately (summarization degrades gracefully with no summary, `/ask` returns a `502` until then).

Starting from an empty database and want something to look at immediately? Seed a handful of sample documents (no dependencies needed beyond Python itself):

```bash
python scripts/seed_demo_data.py
```

## Quick start (local, without Docker)

Each service has its own virtual environment and `requirements.txt` — see that service's own README for details. From a service directory:

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8001   # or 8002 for reporting-service
```

Streamlit:

```bash
cd streamlit-app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run Home.py
```
