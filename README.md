# Doc Digest

An AI-assisted document processing & learning platform: upload documents (PDFs, chapters, notes), run automated processing (metadata extraction, configurable checks), track workflow status, and view aggregate metrics on a dashboard.

Two independently deployable FastAPI microservices ([`document-service`](./document-service/README.md), [`reporting-service`](./reporting-service/README.md)) plus a [Streamlit UI](./streamlit-app/README.md), backed by PostgreSQL. Each service's own README has endpoint tables, local-run instructions, and its `.env` variables — this file covers running the whole stack together.

- **Architecture, conventions, repo layout:** see [`CLAUDE.md`](./CLAUDE.md)
- **Concept-by-concept explanations as the project is built:** see [`LEARNING.md`](./LEARNING.md)
- **Deferred v2+ upgrades and why:** see [`ROADMAP.md`](./ROADMAP.md)

## Status

Phases 0–6 done — the full pipeline (upload → async processing → tracking → reporting → UI), containerized with multi-stage non-root Docker images. See `CLAUDE.md`'s "Project phases" section for the detailed checklist.

**Planned next:** AI-assisted summarization and multi-turn Q&A over uploaded learning material, powered by a self-hosted open-source LLM (Ollama, Llama 3.1) — not yet implemented.

## Quick start (Docker Compose)

```bash
docker compose up --build
```

- Streamlit UI → http://localhost:8501
- `document-service` → http://localhost:8001/docs
- `reporting-service` → http://localhost:8002/docs

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
