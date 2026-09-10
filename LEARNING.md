# LEARNING.md

This is your teaching doc. Each phase gets a section explaining what we built and the theory behind it — assume no prior knowledge of each topic the first time it comes up. Read a section after we finish the corresponding phase, or before if you want the theory first.

---

## Phase 0 — Repo, environment & skeleton

### Why two separate services instead of one app?

A **monolith** is one application handling everything (upload, processing, reporting, UI logic) in one codebase, one process, one deploy. A **microservice architecture** splits responsibilities into independently deployable services that talk to each other over the network (usually HTTP).

Why split here? Document management (upload, storage, workflow state) and reporting (aggregation, metrics) have different jobs, different scaling needs (reporting is read-heavy; document management is write-heavy), and — the reason we picked it for *this* project — different rates of change. You can change how a report is calculated without redeploying the upload pipeline, and vice versa.

The cost of splitting: you trade in-process function calls (fast, reliable, same failure domain) for network calls (slower, can fail independently, need error handling, versioning, and a stable contract). This is why microservices are a genuine trade-off, not a free upgrade — plenty of production systems are monoliths on purpose. We're doing it here partly because it matches the target job description, and partly because it's a good excuse to learn the pattern properly.

### Database-per-service vs shared database

We chose **database-per-service**: `document-service` is the only service that touches Postgres. `reporting-service` gets its data by calling `document-service`'s REST API and computing aggregates itself.

The alternative — both services reading the same Postgres tables directly — is faster to build and query but couples the two services through their database schema. A column rename in `document-service` would silently break `reporting-service`'s SQL with no compiler or type-checker to catch it. Sam Newman's *Building Microservices* calls this the "shared database anti-pattern" for exactly that reason: it looks like two services, but they can't actually be changed or deployed independently, which is the entire point of splitting them.

By making the HTTP API the *only* contract between the two services, a breaking change becomes visible (a failing test, a 4xx response, a schema-validation error) instead of a silent wrong number on a dashboard.

### What is FastAPI, and why use it here

FastAPI is a Python web framework for building APIs. Two things make it a good fit for this project:

1. **Pydantic integration.** You declare the *shape* of a request/response as a Python class (a "schema"), and FastAPI validates incoming data against it automatically, returning a clear 422 error if it doesn't match — instead of you writing manual `if` checks everywhere.
2. **Automatic docs.** FastAPI generates interactive OpenAPI docs (visit `/docs` on a running service) from your route definitions and schemas for free, which is invaluable both for testing manually and for one service to understand another's contract.

### What is Streamlit, and why use it here

Streamlit is a Python framework for building simple, data-oriented web UIs without writing HTML/CSS/JS — you write a Python script that produces widgets (file uploaders, tables, charts) top-to-bottom, and Streamlit re-runs the script on every interaction. It's a good fit for an internal dashboard/tool like this one, where the priority is "show data and take simple input" rather than a highly custom user experience.

### What is Docker / Docker Compose, and why use it here

**Docker** packages an application plus everything it needs to run (Python version, dependencies, OS libraries) into an image, so "works on my machine" becomes "works in this container, on any machine with Docker." A **Dockerfile** is the recipe for building that image.

**Docker Compose** lets you define *multiple* containers (here: Postgres, `document-service`, `reporting-service`, `streamlit-app`) and how they network together, in one YAML file, and bring the whole stack up with one command (`docker compose up`). Inside a Compose network, containers can reach each other by service name (e.g. `document-service` can be reached at `http://document-service:8001` from inside the `reporting-service` container) — no manual IP management.

### Configuration via environment variables (`pydantic-settings`)

Hardcoding things like a database URL or a port number directly in code means you have to edit code to change environment (local vs Docker vs eventually a real cloud deployment). The standard fix — part of the well-known "12-factor app" methodology for building deployable services — is to read configuration from **environment variables** at startup.

`pydantic-settings` is a small library that lets you declare a `Settings` class (e.g. `database_url: str`, `debug: bool = False`) and it automatically populates it from environment variables (and/or a `.env` file), with the same validation guarantees Pydantic gives you for API requests. Each service ships a `.env.example` (documenting what variables it needs, with placeholder values) that gets copied to a real `.env` (which is gitignored, since it may hold real secrets/credentials later).

### Why Alembic instead of `Base.metadata.create_all()`

SQLAlchemy can auto-create tables from your models with one call, which is fine for a quick prototype but breaks down the moment you need to *change* a table that already has data in it (add a column, rename one, add an index) without losing anything. **Alembic** is SQLAlchemy's migration tool: each schema change becomes a versioned, reviewable Python script (a "migration") that can be applied (`upgrade`) or reversed (`downgrade`). This is standard practice for any service with a real, persistent database — which is why only `document-service` (the one that owns the DB) uses it.

---

## Phase 1 — document-service: data model + upload API

### SQLAlchemy: what an ORM actually does

SQLAlchemy is an **ORM** (Object-Relational Mapper): it lets you describe a database table as a Python class (`class Document(Base): ...`) and work with rows as Python objects (`document.status`) instead of writing raw SQL strings everywhere. Under the hood it still generates SQL — `db.query(Document).filter(...)` becomes a real `SELECT ... FROM documents WHERE ...` — but you get type checking, autocomplete, and protection from SQL-injection-by-string-concatenation for free.

We used SQLAlchemy 2.0's newer typed style: `id: Mapped[uuid.UUID] = mapped_column(...)`. The `Mapped[...]` annotation is what lets type checkers and editors know that `document.id` is a `uuid.UUID`, not just "whatever the database returns." Older SQLAlchemy code (and a lot of tutorials) uses untyped `Column(...)` instead — both work, but the typed style catches more mistakes before runtime.

### Why UUIDs instead of auto-incrementing integers for the primary key

An auto-incrementing integer ID (`1, 2, 3, ...`) is simple but leaks information (a competitor can guess how many documents you have from the ID) and becomes a real headache the moment you have multiple services or database instances generating IDs (two services could both hand out `id=57` for different rows). A UUID (`d6f45d9a-b557-...`) is generated independently, essentially never collides, and reveals nothing about volume or order. The trade-off: UUIDs are bigger (16 bytes vs 4-8) and don't sort chronologically the way sequential integers do — which is why `created_at` is a separate column used for ordering, not the ID itself.

We used SQLAlchemy's cross-dialect `Uuid` type rather than `postgresql.UUID` specifically — the generic one stores as a native UUID column on Postgres but degrades gracefully to a plain string column on databases without native UUID support (like SQLite), which is exactly what let us test against SQLite without any special-casing.

### Alembic in practice: autogenerate, review, apply

The actual workflow, now that it's set up: change a model → `alembic revision --autogenerate -m "description"` (Alembic diffs your models against the last known schema and writes a migration script) → **read the generated file** (autogenerate is a helpful diffing tool, not an oracle — it can miss renames, index changes, or get a default value subtly wrong) → `alembic upgrade head` (applies it). Each migration has an `upgrade()` and a `downgrade()`, so a bad migration can, in principle, be reversed.

One concrete lesson from building this: `DocumentStatus` declares all four states (`UPLOADED/PROCESSING/COMPLETED/FAILED`) even though Phase 1 only ever sets `UPLOADED`. That's deliberate — Postgres represents a Python `Enum` as a native `ENUM` type in the database, and altering an existing Postgres enum type to add new values is more awkward than a normal column migration (historically it couldn't even run inside the same transaction as other DDL). Defining the full, known vocabulary in the first migration sidesteps that entirely — a small example of a database constraint shaping an application-level design decision.

### FastAPI dependency injection for DB sessions

Every route that needs the database declares `db: Session = Depends(get_db)`. `get_db` is a generator function that opens a session, `yield`s it to the route, and closes it in a `finally` block once the route is done — FastAPI runs the code before the `yield` before your route, and the code after it after your route returns, guaranteeing the session is closed even if the route raises an exception. This pattern (a dependency that "wraps" the request) is how FastAPI does most of its resource management, and it's also what makes testing easy: `app.dependency_overrides[get_db] = <test version>` swaps in a completely different database for tests, with the route code never knowing the difference.

### Streaming file uploads instead of loading them into memory

`save_upload_file` reads the incoming file in fixed-size chunks (`upload_file.file.read(CHUNK_SIZE)`) and writes each chunk to disk immediately, rather than doing `content = upload_file.file.read()` (which pulls the *entire* file into memory before writing anything). For a 20 MB PDF this barely matters; for a service that might one day accept much larger files from many concurrent users, reading everything into memory at once is how a server runs out of RAM under load. Streaming also let us enforce the size limit *while* reading — we can abort and delete the partial file the moment it exceeds the limit, instead of only finding out after the whole file was already received.

### Why the API schema (`DocumentRead`) is a separate class from the ORM model

`Document` (the SQLAlchemy model) describes what's in the database — including `file_path`, the actual location on disk. `DocumentRead` (the Pydantic schema) describes what the API returns — and deliberately omits `file_path`, since there's no reason to expose the server's internal filesystem layout to an API client. Pydantic's `model_config = ConfigDict(from_attributes=True)` is what lets a `DocumentRead` be built directly from a `Document` ORM instance (reading its attributes) without manually copying each field over. Keeping these separate means the database schema and the public API contract can evolve independently — a lesson that also applies at the service level (see Phase 0's database-per-service discussion).

### Testing with SQLite instead of the real Postgres

The test suite (`tests/conftest.py`) spins up a fresh **in-memory SQLite database** for every test via a `client` fixture, instead of hitting the real Postgres instance. This is a deliberate trade-off: SQLite starts instantly and needs no running service, so the whole test suite runs in well under a second — but SQLite isn't Postgres, and a few Postgres-specific behaviors (certain constraint enforcement details, some SQL functions) wouldn't be caught this way. For a project this size, fast/isolated unit tests against SQLite plus manual/integration verification against the real containerized Postgres (which we also did, by hand, after building this) is a reasonable balance. A larger production system often adds a dedicated integration test suite that runs against a real (often ephemeral/dockerized) Postgres in CI specifically to catch that gap — noted as a natural CI/CD-phase addition in `ROADMAP.md`.

`monkeypatch` (a built-in pytest fixture) is what let tests temporarily override a `Settings` value (like `max_upload_size_bytes`) for a single test and have it automatically restored afterward — useful for testing edge cases like the size-limit rejection without changing the real default.

### A real bug this process caught: dead validation code

While testing, uploading a file with an empty filename returned `422`, not the `400` the route explicitly raised for that case. The reason: FastAPI/Starlette's own multipart-parsing validation was already rejecting the malformed request *before* our route function ever ran — so the `if not file.filename: raise HTTPException(400, ...)` line was unreachable dead code, just one layer of "defense" that never actually got exercised. Writing the test surfaced this; the fix was deleting the check (not catching it) rather than making the test match a bug. Worth remembering generally: when a test fails in a surprising way, check whether the *test's assumption* is wrong before assuming the code is.

### A real environment issue this process caught: port collisions

`docker compose up -d postgres` succeeded, but Alembic's connection then failed with a Postgres *authentication* error — misleading, because it looked like a credentials bug. The actual cause: this machine already had a **native PostgreSQL install** listening on port 5432, and Docker's port-forwarding for `localhost:5432` was colliding with it — so the connection was silently reaching the wrong Postgres server entirely, one with different credentials. The fix was mapping the container to a different host port (`5433:5432` in `docker-compose.yml`) — the container's *internal* port stays 5432 (that's what other containers use to reach it via `postgres:5432` inside the Compose network), only the host-side mapping changed. This is a good illustration of why Docker networking has two separate "sides": the network inside Compose (service names, unaffected by host port choices) and the mapping to the host machine (which can collide with anything else already running there).

---

## Phase 2 — document-service: async processing workflow

### FastAPI BackgroundTasks: what "async" means here

`BackgroundTasks` is FastAPI's simplest way to run code *after* a response has already been sent to the client. The upload route adds a job with `background_tasks.add_task(process_document, document.id)`, returns the `201 Created` response immediately (with `status: "UPLOADED"`), and then — after the response is on the wire — FastAPI runs `process_document` in the same process.

This is "async" in the sense that the *client* doesn't wait for processing to finish, but it's important to be clear about what it isn't: it's not a separate worker, not persistent (if the server process crashes mid-task, the job is just gone, with no record that it was supposed to run), and it still runs on the same machine competing for the same resources as everything else the server is doing. That's exactly the gap `ROADMAP.md` names for the Celery+Redis upgrade — a real task queue gives you persistence, retries, and dedicated worker processes. `BackgroundTasks` is the right amount of machinery for "kick off some quick work after responding" at this project's current scale; it stops being the right tool once jobs get slow, need retries, or must survive a restart.

### Why the background task opens its own DB session

The route's DB session (from `Depends(get_db)`) is closed the moment the route function returns — that's what the `finally: db.close()` in `get_db` guarantees. `process_document` runs *after* that point, so it can't reuse the request's session; it has to open a fresh one (`SessionLocal()`) and close it itself when done. This is a general rule for background work in FastAPI: anything that outlives the request needs its own resources, because everything scoped to the request (including `Depends`-injected sessions) is gone once the response is sent.

### The state machine, and why every transition is logged instead of just the final status

`Document.status` only ever holds the *current* state, but `ProcessingHistory` records *every* transition (`from_status`, `to_status`, a `message`, a timestamp) as an append-only log. This is a small example of a broader, very common pattern: when "what is true right now" isn't enough and you also need "how did we get here" (for debugging, for showing a user a timeline, for an audit trail), you keep the current-state column for fast lookups *and* a separate append-only event log for history — rather than trying to reconstruct history from a single mutable field, which is impossible once it's overwritten.

### Checks as a list of functions, not a big `if` chain

`app/services/checks.py` defines each check as a small function `Document -> CheckResult`, collected in a `CHECKS` list that `process_document` just loops over. Adding a new check later means writing one more small function and appending it to the list — no existing code has to change. This is a lightweight version of the "strategy pattern" (interchangeable behaviors behind a common shape) — deliberately *not* a full rules engine (rules defined in a database/config file, evaluated generically): that's a real upgrade path, tracked in `ROADMAP.md`, but would be over-engineering for two checks.

### Two real issues this process caught (both fixed, both instructive)

**1. The background task was silently writing to the wrong database.** `process_document` imports `SessionLocal` directly from `app/db/session.py` — which is bound to whatever `settings.database_url` points at. In tests, the *route* handlers correctly used the test SQLite database (via the `get_db` dependency override), but the *background task* doesn't go through any FastAPI dependency — it's just a plain function call — so it kept using the real configured database underneath the test. The first test run "passed" in the sense that nothing crashed, but every document stayed stuck at `UPLOADED` because the assertions were checking the test DB while the actual status update landed somewhere else entirely. The fix (`tests/conftest.py`): `monkeypatch.setattr("app.services.processing.SessionLocal", testing_session_local)` — patching the *specific reference* that `processing.py` holds, not the original definition in `db/session.py`. This is a good general lesson about Python's import system: `from module import name` copies a reference into the importing module's namespace; patching `module.name` afterward does **not** change what `other_module.name` points to, because `other_module` already has its own copy of that reference. You have to patch it where it's *used*, not where it's *defined*.

**2. A subtle SQLAlchemy/Postgres ENUM bug, tracked down empirically.** Adding `ProcessingHistory.from_status`/`to_status` (both referencing the *already-existing* `document_status` Postgres enum type) should have been solved by the generic `sa.Enum(..., create_type=False)` flag — and it partially was: `create_type=False` worked correctly under `Base.metadata.create_all()` (what the SQLite tests use) but still triggered a duplicate `CREATE TYPE` error under `Table.create(conn, checkfirst=False)` — which is what Alembic's `op.create_table` actually calls internally. Reading SQLAlchemy's own source confirmed why: `create_type` is a parameter that genuinely belongs to `sqlalchemy.dialects.postgresql.ENUM` (the Postgres-specific type), and the generic cross-dialect `sa.Enum(...)` doesn't reliably forward it to the Postgres implementation on every code path. The fix was using `from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM` directly in the migration file instead of the generic `sa.Enum(...)`. The broader lesson: when a library's documented parameter doesn't behave as documented, isolate the *smallest possible reproduction* (a five-line script, not the whole app) before guessing at a fix — it turned a confusing "why does this keep failing the same way after my fix" into a five-minute, evidence-based diagnosis.

---

## Phase 3 — reporting-service: HTTP-only aggregation API

### Designing the contract, not just the code

Once `reporting-service` has no database of its own, `document-service`'s public API becomes the *entire* interface between the two services — there's nothing else to fall back on. That raises the stakes on API design in a way a single-database app never has to think about: every field `document-service` returns (or doesn't) directly determines what `reporting-service` can compute. This project's `GET /api/v1/documents` already returned `status`, `created_at`, and `updated_at` for Phase 1 reasons unrelated to reporting — and it turned out those three fields were *enough* to build all three reports without adding a single new endpoint. That's not an accident to rely on going forward, though: any future report needing data the list endpoint doesn't expose would need a deliberate, versioned change to the contract — not a workaround on the reporting side.

### Approximating "processing time" instead of measuring it exactly

`ProcessingStatsReport.average_processing_seconds` is computed as `updated_at - created_at` for documents in a terminal state (`COMPLETED`/`FAILED`). This works because `_transition()` in `document-service` touches `updated_at` on *every* status change, so for a finished document, `updated_at` happens to equal the moment it finished. But this is an approximation, not a direct measurement: it includes any time the document spent in `UPLOADED` *before* processing even started (in this codebase that's near-zero, since the background task kicks off immediately after upload — but nothing guarantees that stays true). An exact measurement would need document-service to expose something like "time entered PROCESSING" specifically (from `ProcessingHistory`), which would mean either a bulk history endpoint or embedding that timestamp directly on `Document`. Choosing the cheap-but-approximate option here — one field already available on every document, versus a new endpoint or an N+1 fetch pattern (list, then fetch every document's history individually) — is a real, common trade-off: exact-but-expensive vs. approximate-but-simple. The right choice depends on how much the approximation error actually matters for what the number is used for; a dashboard showing "documents complete in about half a second on average" doesn't need millisecond precision.

### Why `reporting-service` duplicates `DocumentStatus` instead of importing it

`document-service` has `DocumentStatus` as a Python enum in `app/models/document.py`. `reporting-service` has its *own*, separately-defined `DocumentStatus` in `app/schemas/document.py` with the identical four values — not an import of the first one. This looks redundant, but it's the direct consequence of Phase 0's decision to keep the two services decoupled at the *code* level, not just the database level: if `reporting-service` imported `document-service`'s Python module, the two services would need to ship as one deployable unit (or duplicate the file via some build step), defeating the point of them being independent services with independent deploys. The cost is real and worth naming plainly: if `document-service` ever adds a fifth status, `reporting-service`'s copy has to be updated by hand, and nothing will automatically catch a missed update except a test or a runtime validation error. Larger systems solve this with **generated clients** — a tool reads `document-service`'s OpenAPI schema (which FastAPI produces automatically) and generates `reporting-service`'s client code, so the "duplicate" stays mechanically in sync instead of manually — a natural next upgrade once the contract has more than a couple of shapes to keep aligned.

### FastAPI `Depends` for swappable dependencies, not just DB sessions

Phase 1 used `Depends(get_db)` specifically for database sessions, but the same mechanism is more general: `get_document_service_client` is a `Depends` too, and the *only* reason `reporting-service`'s tests don't need a real running `document-service` is that `app.dependency_overrides[get_document_service_client] = lambda: fake_client` swaps in a fake with a canned response — same trick as swapping SQLite in for Postgres in Phase 1's tests, applied to an HTTP client instead of a DB session. Once a route's dependencies are all expressed as `Depends(...)`, *anything* that route needs from the outside world becomes independently swappable for testing.

### `httpx.MockTransport`: testing an HTTP client without a network

`tests/test_document_service_client.py` tests `DocumentServiceClient.fetch_all_documents()` directly — not through a FastAPI route — by constructing an `httpx.AsyncClient` with a custom `transport` argument (`httpx.MockTransport(handler)`) instead of a real network transport. The `handler` function receives each outgoing `httpx.Request` and returns a synthetic `httpx.Response`, so the client's actual pagination logic (looping on `skip`/`limit` until a short page) runs for real against fake data, with no server, no sockets, and no timing flakiness. This is a different testing layer than the `fake_client`/`Depends` trick above: that one tests "does the *route* behave correctly given some documents," this one tests "does the *client* correctly implement HTTP pagination and error handling" — two different failure modes, both worth covering independently.

### `502 Bad Gateway`: the correct status code for "my dependency failed"

When `document-service` is unreachable, `reporting-service` returns `HTTP 502`, not `500`. The distinction matters and is a real piece of HTTP semantics: `500 Internal Server Error` means *this* server hit a bug or unhandled condition; `502 Bad Gateway` specifically means *this* server is fine, but a service it depends on to fulfill the request failed or returned something invalid. Since `reporting-service`'s entire job now depends on `document-service` being reachable, using the status code that says exactly that — "I'm working, but my upstream isn't" — gives a monitoring dashboard or an on-call engineer immediately more useful information than a generic 500 would, without them having to go read logs to find out which of the two services is actually broken.

---

## Phase 4 — Streamlit UI

### How Streamlit's multipage app mechanism works

Streamlit turns a plain folder convention into a navigable app: `app.py` is the entry point, and any `.py` file inside a `pages/` directory next to it becomes a separate page, automatically listed in the sidebar. The filename becomes the nav label — Streamlit strips a leading `N_` ordering prefix and turns underscores into spaces, which is why `pages/1_Upload.py`, `pages/2_Documents.py`, `pages/3_Dashboard.py` show up in the sidebar, in that order, as "Upload", "Documents", "Dashboard". There's no router, no URL-to-component mapping to configure — the filesystem *is* the navigation structure. This is a deliberate simplicity trade-off (Streamlit's audience is data/internal tooling, not public-facing apps), and it's why sharing code between pages works by ordinary Python import (`from api_client import ...`) rather than a framework-provided mechanism — Streamlit just ensures the project root is on `sys.path` when it runs a page.

### Streamlit's execution model: the whole script reruns on every interaction

Streamlit doesn't have component-level state updates the way a typical JS framework does — every time a user does *anything* on a page (clicks a button, changes a dropdown, types in a box), Streamlit reruns the **entire page script from top to bottom**. `pages/2_Documents.py` re-fetches the document list and re-renders the whole page every time you pick a different document from the "Select a document" dropdown — that's not inefficient code, it's simply how Streamlit works. This is why the Upload page's `if uploaded_file is not None and st.button("Upload", type="primary")` pattern matters: without a real interactive DOM, "only run the upload once the button is clicked" *is* the button-click triggering a full script rerun where `st.button(...)` evaluates to `True` for exactly that one rerun.

### Why a thin API client module, not `requests.get()` scattered across pages

`api_client.py` centralizes every HTTP call (and, importantly, error handling — pulling a FastAPI error response's `detail` field out of a failed request) in one place, so each page just calls `list_documents()` or `get_summary_report()` and gets back either data or a clean `ApiError` to catch. This is the same instinct as `document-service`'s router/service split or `reporting-service`'s dedicated `DocumentServiceClient` — keep "how do I talk to this other thing" separate from "what do I do with the result" — just applied to a UI instead of another service.

### Designing for a state you don't own

Uploading a document doesn't immediately show it as `COMPLETED` — processing happens in a background task on `document-service`, invisible to `streamlit-app`. The Upload page is explicit about this ("Processing runs in the background... check the Documents page a moment later"), and the Documents/Dashboard pages have a manual **Refresh** button (`st.rerun()`) rather than pretending the data is always current. This is a real UI design question any time a frontend sits in front of asynchronous backend work: pretending state is instantly consistent (and having the UI quietly lie) is worse than being explicit that a refresh is needed. A fancier version — auto-polling until a document leaves `PROCESSING` — is a reasonable later enhancement, but even that would still be *polling*, not real-time push; true real-time would need WebSockets or server-sent events, a bigger architectural addition than this UI needs yet.

### Choosing status colors deliberately, not by default

The dashboard's bar chart assigns explicit colors to each document status — blue for `UPLOADED` (a neutral, non-severity "queued" state), amber for `PROCESSING` (in flux), green for `COMPLETED`, red for `FAILED` — rather than accepting whatever colors a charting library's default palette hands out. This matters for a status chart specifically: default categorical palettes are chosen for *distinguishability between arbitrary categories*, not for *meaning* — a viewer's brain reads red as "bad" and green as "good" regardless of what a legend says, so a chart that accidentally colored `FAILED` green would actively mislead at a glance. Assigning color *by the role it plays* (a fixed "good/warning/critical" vocabulary) rather than cycling through a generic palette is a small example of a broader principle: in any dashboard, color should encode meaning on purpose, not fall out of a library default.

### Testing a UI for real: headless-browser automation over HTTP status checks

Every earlier phase's "verification" involved curl and pytest — enough for an API, because an API's correctness *is* its response bytes. A UI is different: a page can return `200 OK` while being completely blank, or throwing a JavaScript error the instant a user clicks something, and a status-code check would never catch either. This phase used Playwright (a browser-automation library) driving real headless Chromium — navigating pages, clicking Streamlit's actual rendered dropdown, uploading a real file through the real file input, and reading back both screenshots and the browser's console — to verify what a user would actually experience, not just what the server returned. Two real defects a pure HTTP check would have missed were avoided by finding them from behavior (a wrong CSS selector guess for Streamlit's dropdown, an oversized Docker build context from a missing `.dockerignore`) — the second one wasn't even a UI bug, but wouldn't have surfaced without actually running a full `docker compose up --build` and watching what got sent.

### Addendum — downloading the original file: internal vs. public URLs

A natural next question once the UI existed: can you actually get the uploaded file back out? Answering it surfaced a design point worth naming explicitly.

`document-service` lives at `http://document-service:8001` *inside* the Docker Compose network — that hostname only resolves for other containers on that same network. It's also reachable at `http://localhost:8001` from the host machine, because of the port mapping in `docker-compose.yml`. Those are two different addresses for two different audiences: `streamlit-app`'s own Python code (running inside a container) must use the internal one; a link meant to be *clicked by the user's browser* would need the host-facing one instead — and a browser has no idea what `document-service:8001` even is.

Rather than juggle two separate URLs (and have the UI behave differently depending on whether it's running in Docker or standalone), the cleaner fix was to never let the browser talk to `document-service` at all: `streamlit-app` fetches the file's bytes itself (server-side, using the internal URL, which always works since that call never leaves the Docker network) and then hands those bytes to the browser via `st.download_button`, which serves them from the connection the browser *already has open* to Streamlit. One consistent rule — "the browser only ever talks to streamlit-app" — replaces what would otherwise be an environment-dependent special case.

The other small decision: the "Load file" step is gated behind an explicit button rather than fetching automatically. Recall from earlier in this phase that Streamlit reruns the *entire* page script on every interaction — without the button, selecting a different filter, or even just scrolling in a way that triggers a rerun, would silently re-download a file (up to 20MB) that the user never asked to load. Making the fetch opt-in avoids paying that cost for interactions that have nothing to do with the file itself.

### Addendum — UI iteration: entry-point naming, merging a page, search, and revisiting the fetch trade-off

A few follow-up refinements, each a small lesson on its own:

**The sidebar label for the entry-point script is just its filename.** Streamlit doesn't title-case or reformat the entry point's name the way it does for `pages/N_Name.py` files — it shows exactly what the file is called. Renaming `app.py` to `Home.py` was the entire fix for the sidebar showing "Home" instead of "app"; no configuration flag involved.

**Folding Upload into Home** removed a page but not a feature — the upload widget, button, and success handling moved into `Home.py` verbatim. This is a reminder that Streamlit's page-per-file structure is purely organizational: nothing about *how* `st.file_uploader`/`st.button` work changes based on which script they live in.

**The filename search** (`pages/1_Documents.py`) filters the *Python list* of documents by substring before building the "Select a document" dropdown's options — `[d for d in documents if search_query.lower() in d["filename"].lower()]`. Worth noting: `st.text_input` only triggers a script rerun when the field loses focus or Enter is pressed (there's a visible "Press Enter to apply" hint while text is uncommitted) — this is deliberate on Streamlit's part, so the whole page doesn't rerun on every single keystroke.

**Revisiting the "Load file" gate — with `st.session_state` instead of a second click.** Phase 4 originally put the file fetch behind an explicit button to avoid re-downloading on every rerun. The better fix, used here instead: `st.session_state.setdefault("document_content_cache", {})`, keyed by document ID. The first time a document is selected, its bytes get fetched and cached; every subsequent rerun — a status-filter change, a search, clicking Refresh — checks the cache first and only calls `document-service` again if that specific document's bytes aren't already there. The download button still renders immediately, with no extra click, but the network call only happens once per document per browser session.

Two things worth knowing about why this works and how it was verified. First, `st.session_state` is *exactly* the mechanism Streamlit provides for surviving `st.rerun()` and ordinary widget-triggered reruns — unlike a plain Python variable (which resets every time the script re-executes top to bottom), values placed in `session_state` persist for the life of that browser session. Second, verifying this claim honestly required catching a mistake: the first attempt to measure "how many times does `/content` get hit" used `docker compose restart` between test runs to get a clean log, but **`restart` doesn't clear a container's log history** — Docker keeps appending to the same log stream across a restart, only `down`/`up` (which recreates the container) does. That produced confusing, inflated counts that looked like the cache wasn't working. Switching to `docker compose logs --since <timestamp>` — scoping the query to a time window instead of relying on a "clean" log — gave an accurate count and confirmed the cache genuinely works: exactly one `/content` request per selected document, no matter how many unrelated reruns followed. A reminder that a suspicious measurement is sometimes the measurement's fault, not the code's — worth ruling out before trusting a surprising number.

---

## Phase 5 — containerize everything properly

Most of "containerizing" had already happened by necessity, since every phase since Phase 0 was verified against real Docker Compose runs. What was actually left: multi-stage builds and non-root containers — two related but distinct hardening steps.

### Multi-stage builds: separating "install" from "run"

Every Dockerfile now has two `FROM` lines: a `builder` stage that runs `pip install --user -r requirements.txt`, and a separate runtime stage that only copies the *result* of that install (`/root/.local` → the final image) plus the application code — never the `requirements.txt`-processing tooling itself. The final image never contains pip's download cache, and if a dependency ever needed a C compiler to build (this project's don't — see below), the compiler itself would live only in the discarded `builder` stage, never shipping in what actually runs in production. The pattern in one line: **build stages produce artifacts; only the last stage in the file becomes the image that runs.**

Worth being honest about the actual payoff here: multi-stage builds are usually sold on *image size*, but none of this project's dependencies need to compile anything (`psycopg2-binary` is explicitly the pre-compiled variant; everything else ships prebuilt wheels), so there was no bloated build-toolchain to strip out. The real benefit realized here is the *separation itself* — a clean boundary between "what it takes to prepare this image" and "what actually runs" — which is what made adding a non-root user straightforward next.

### Running as a non-root user

`RUN useradd --create-home --uid 1000 appuser` plus `USER appuser` near the end of each Dockerfile. Without this, every container runs as `root` by default — meaning a vulnerability in the application code (or in any of its dependencies) that achieves arbitrary code execution would run with root privileges *inside that container*. That's a smaller blast radius than root on the host, but it's still needlessly more access than the app ever legitimately needs — it only has to read its own code, write to one upload directory, and talk over HTTP. "Run as the least-privileged user that can still do the job" is a general security principle (the same idea behind a database role that can only `SELECT`, or a cloud IAM policy scoped to one bucket); non-root containers are that principle applied to Docker specifically.

### A real bug this caused, and why it happened

Switching `document-service` to non-root immediately broke uploads — a clean `500 Internal Server Error`. The cause: `document-service`'s upload storage directory (`/app/storage`) is a Docker **named volume**, mounted from `docker-compose.yml`, and that volume had been created *earlier*, back when the container still ran as root — so its on-disk ownership was `root:root`. Rebuilding the image with a new non-root user changes what the *image* contains, but a named volume's existing content and ownership are independent of the image — Docker doesn't retroactively re-apply new ownership to a volume that already exists. The non-root `appuser` simply didn't have write permission to a directory still owned by `root`.

The fix was two parts. First, in the Dockerfile: `RUN mkdir -p storage && chown -R appuser:appuser /app` *before* `USER appuser` — this ensures that if Docker ever needs to initialize a **brand-new** volume at that mount path, it copies the image's existing directory (already correctly owned) into the fresh volume, which is a real (if slightly obscure) Docker behavior: on first use, a named volume inherits whatever was already at that path in the image. Second, for the volume that already existed from before this change: removing it (`docker volume rm ...`) so Docker recreated it fresh, correctly inheriting the new ownership. That second part was a one-time migration step, not something the Dockerfile itself could fix — no image change can retroactively alter a volume that already exists with different content.

---

## Phase 6 — polish v1

### Logging: `print()` doesn't survive the reason you needed it

Before this phase, the only visibility into what `process_document` was doing came from reading database rows after the fact. `logging.basicConfig(...)` plus `logger.info(...)` calls at each state transition means an operator can watch `docker compose logs -f document-service` and see, in real time, exactly what the background pipeline is doing and why a document failed — without needing to separately query the database. The specific format used (`%(asctime)s %(levelname)s %(name)s: %(message)s`) is a deliberately minimal, human-readable one; `ROADMAP.md`'s "structured logging" entry (JSON logs, correlation IDs) is the natural next step once logs need to be machine-parsed by something like an aggregator, not just read directly.

One small but real detail: `logger.info("...", from_status.value, ...)` uses `.value` rather than logging the `DocumentStatus` enum member directly. `str(some_enum_member)` for a `class X(str, Enum)` (this project's style) actually prints `"DocumentStatus.UPLOADED"`, not `"UPLOADED"` — a well-known Python surprise, since being a `str` subclass doesn't change what `Enum.__str__` returns. Worth remembering any time an enum ends up in an f-string or a `%s`.

### A global exception handler: turning "silent 500" into "logged, safe, consistent 500"

Without `@app.exception_handler(Exception)`, an unexpected error (a bug, a permission problem, a dropped DB connection) produces Starlette's bare default: plain text `"Internal Server Error"`, no logging, and a response shape that doesn't match the JSON `{"detail": "..."}` every other error in this API returns. This project hit that exact scenario for real, during the Phase 5 volume-permission bug — the response gave no hint *why* it failed, and nothing was logged server-side to explain it either. The handler added here fixes both problems at once: `logger.exception(...)` records the full traceback (so the *next* time something like this happens, the cause is in the logs, not just the symptom), and the client still gets a safe, generic, consistently-shaped error — deliberately generic, since leaking a raw exception message or traceback to an API client can expose internal details (file paths, library versions, query structure) that are useful to an attacker and not useful to a legitimate caller.

`reporting-service` layers a second, more specific handler on top: `DocumentServiceError` → `502`, registered once in `main.py` instead of wrapped in a `try/except` in every route. This is the general shape worth remembering: **the most specific applicable handler wins**, so a catch-all `Exception` handler and a handler for one particular exception type can coexist without conflict — FastAPI dispatches to whichever registered handler most precisely matches what was actually raised.

### A FastAPI testing subtlety: `TestClient`'s `raise_server_exceptions`

Writing a test to prove the catch-all handler actually works (not just "it looks right") surfaced a genuine `TestClient` behavior worth knowing generally: by default, `TestClient` **re-raises** any exception that results in a 500 response straight into the test — even one that an app-level `@app.exception_handler(Exception)` already caught and converted into a normal-looking response. This is deliberate: it's what makes an unexpected bug fail a test loudly, instead of the test quietly asserting on a 500 status code and missing that something is actually broken. But it means the *one* test that specifically wants to observe "what does a real client actually receive when the catch-all handler fires" has to opt out, explicitly: `TestClient(app, raise_server_exceptions=False)`. Handlers for a *specific* exception type (like `DocumentServiceError`) don't trigger this re-raising — only the generic `Exception` catch-all does, since Starlette treats "some specific, expected failure mode was handled" differently from "something genuinely unanticipated happened, but a safety-net handler caught it anyway."

### A dependency-free seed script, on purpose

`scripts/seed_demo_data.py` uses only `urllib.request` and `argparse` from the standard library — no `requests`, nothing from any service's own `requirements.txt`. The reasoning: a "run this to see sample data" script should have the lowest possible barrier to actually running it — anyone with plain Python 3 and the stack already up via `docker compose up` can run it immediately, with no venv to create or activate first. It also deliberately seeds both success *and* failure cases (a disallowed extension, an empty file) rather than only happy-path documents, so a fresh run demonstrates the whole workflow — including the parts of the system (checks, failure messages, history) that only show up when something goes wrong on purpose.

---

*(Later phases — beyond v1 — are tracked in ROADMAP.md rather than appended here.)*
