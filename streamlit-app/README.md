# streamlit-app

The UI. Three pages, all calling `document-service` and `reporting-service` over HTTP — no business logic of its own beyond display/formatting, and no database access. See the root [README](../README.md) and [CLAUDE.md](../CLAUDE.md) for the full architecture.

## Pages

- **`Home.py`** (sidebar: "Home") — upload a PDF or `.txt` file.
- **`pages/1_Documents.py`** ("Documents") — list, filter by status, search by filename, and view any document's metadata, download the original file, and see its full processing-history timeline.
- **`pages/2_Dashboard.py`** ("Dashboard") — stat tiles, a status-colored bar chart, and recent activity, all from `reporting-service`.

Shared HTTP-calling code lives in `api_client.py` at the project root, imported directly by every page.

## Run locally (without Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # point at running document-service/reporting-service
streamlit run Home.py
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DOCUMENT_SERVICE_URL` | `http://localhost:8001` | Base URL this app's Python code calls server-side. |
| `REPORTING_SERVICE_URL` | `http://localhost:8002` | Same, for `reporting-service`. |

Note: the browser never talks to either service directly — everything (including file downloads) is fetched server-side by this app and handed to the browser from there. See `CLAUDE.md`'s Conventions section.
