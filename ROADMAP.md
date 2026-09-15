# ROADMAP.md

Deliberately deferred upgrades — things v1 does *not* do, on purpose, so it stays simple enough to actually finish. Each entry says what it would add, why it's not in v1, and what it would teach. Pull items from here into the phase plan whenever you want to tackle one.

---

## Known gaps from Phase 7 — small, concrete, not yet done

Unlike everything below this line, these two are already scoped and agreed, just not implemented yet — pick them up whenever.

### Ollama's context window isn't actually being used
Ollama defaults every session to `num_ctx: 4096` tokens unless a request explicitly overrides it, and `document-service/app/services/ollama_client.py`'s `chat()` doesn't currently set that option. So despite `summarization.py`'s `MAX_WORDS = 12000` cap (~15,600 tokens) suggesting a generous ceiling, the model can in practice only ever see roughly 3,000 words of a document — anything beyond ~5–10 pages is silently dropped rather than erroring, and summaries/answers quietly degrade instead of failing loudly. Confirmed directly against the running container: `ollama ps` reports `CONTEXT 4096` for the loaded `llama3.1` session, while `ollama show llama3.1` reports the model itself supports up to 131,072.

**The fix:** pass `"options": {"num_ctx": N}` in the `/api/chat` request body in `ollama_client.py`, and lower `MAX_WORDS` (`summarization.py`, reused by `chat.py`) to match so the two numbers agree. RAM math for this model (KV cache ≈ 128KB/token, weights ≈ 5.6GB loaded) says `num_ctx` in the **16384–32768** range is comfortable on a 16GB laptop (≈8.5–10.5GB total including weights + KV cache + OS/Docker overhead) — the full 131072 window would need ~16GB+ for KV cache alone and isn't realistic on this hardware. 16384 (~20–40 pages) is a reasonable starting target.

### Documents page: AI summary should be single-column, not side-by-side
`streamlit-app/pages/1_Documents.py` currently renders the AI summary next to "Extracted metadata" in a two-column layout (`detail_col, metadata_col = st.columns(2)`), which squeezes a multi-paragraph summary into a narrow column and makes it hard to read. Change to a single-column layout: keep the filename/status/etc. fields and extracted metadata as they are, but render the AI summary full-width, below rather than beside them.

---

### Event-driven sync between services (Kafka / RabbitMQ)
Right now `reporting-service` calls `document-service`'s API on demand, every time a report is requested. At real scale this gets slow and puts load on `document-service` for every dashboard refresh. The production-grade fix: `document-service` publishes an event (e.g. "document status changed") to a message broker whenever something happens, and `reporting-service` consumes those events to maintain its *own* local, read-optimized copy of the data — no live API call needed per request. This is the real-world version of the database-per-service pattern, often paired with **CQRS** (Command Query Responsibility Segregation — separate models for writing vs reading data) and sometimes **event sourcing**. Teaches: async messaging, eventual consistency, idempotent consumers.

### Real background job processing (Celery + Redis)
v1 uses FastAPI's `BackgroundTasks`, which runs the job in the same process right after the response — simple, but jobs are lost if the process restarts mid-job, and there's no retry/scheduling/distributed-worker support. **Celery** (a distributed task queue) with **Redis** or RabbitMQ as the message broker gives you persistent job queues, retries with backoff, scheduled/periodic jobs, and the ability to run many worker processes (even on separate machines) pulling from the same queue. Teaches: task queues, worker pools, idempotency, retry strategies.

### OCR / richer text extraction
v1 only extracts basic metadata (page count, word count) from PDFs and plain text. Real document processing platforms often need **OCR** (Optical Character Recognition, e.g. via Tesseract) to pull text out of scanned/image-based PDFs, plus support for more formats (DOCX, images, spreadsheets). Teaches: OCR pipelines, format-specific parsing libraries, handling unstructured/noisy extracted data.

### Object storage (MinIO / S3) instead of local disk
v1 stores uploaded files on a local Docker volume. That's fine for one machine, but doesn't scale horizontally (multiple `document-service` instances need shared storage) and isn't how most production systems store files. **MinIO** (self-hosted, S3-compatible) or actual AWS S3 would replace the local filesystem with an object store accessed over an API, decoupling storage from any one server. Teaches: object storage concepts, pre-signed URLs, blob storage vs block/file storage.

### Authentication & authorization
v1 has no login — anyone who can reach the API can use it. A real platform needs to know *who* is uploading/viewing documents. Options range from simple API keys to full **OAuth2/JWT**-based auth (FastAPI has good built-in support for this), plus role-based access control (e.g. "can this user see this document"). Teaches: auth flows, token-based sessions, authorization vs authentication.

### A real rules engine for "configurable checks"
v1's processing checks (file type allowed, size limit) are a couple of hardcoded `if` statements. A more flexible version would let checks be defined declaratively (e.g. a YAML/JSON rules file, or rows in a database) and evaluated generically, so adding a new check doesn't require a code change/redeploy. Teaches: rules engines, plugin/strategy patterns, data-driven configuration.

### CI/CD pipeline
v1 is tested and run manually. A CI/CD pipeline (e.g. GitHub Actions) would automatically run tests/linting on every push, build Docker images, and optionally deploy on merge. Teaches: continuous integration concepts, automated testing gates, image build/publish workflows.

### Pre-commit hooks & enforced linting/formatting
v1 doesn't enforce code style automatically. Tools like `black` (formatting), `ruff` (linting), and `pre-commit` (runs checks before every commit) keep code consistent without manual review overhead. Teaches: tooling for code quality, git hooks.

### Rate limiting & request throttling
v1's APIs have no limit on how fast a client can call them. Production APIs typically rate-limit per client (e.g. via `slowapi` or a gateway like an API gateway/nginx) to prevent abuse and protect shared resources. Teaches: rate-limiting algorithms (token bucket, sliding window), API gateway patterns.

### Observability: structured logging, metrics, tracing
v1 has basic logging. A production system would add structured (JSON) logs, metrics (e.g. Prometheus counters for documents processed/failed, exposed via `/metrics`), dashboards (Grafana), and distributed tracing (e.g. OpenTelemetry) so a request can be followed across both services. Teaches: the three pillars of observability, correlation IDs, why "it works on my machine" isn't enough in a multi-service system.

### Caching layer for reporting-service
Once `reporting-service` is doing real aggregation over HTTP calls, repeated identical report requests are wasted work. A cache (in-memory TTL cache, or Redis) in front of expensive aggregation queries would cut load on `document-service`. Teaches: cache invalidation strategies, TTL vs event-driven cache busting.

### Horizontal scaling & load balancing
v1 runs one instance of each service. Scaling to multiple instances behind a load balancer (and making sure the app is stateless enough to allow that) is the standard next step for handling more traffic. Teaches: statelessness, load balancing strategies, sticky sessions (and why to avoid needing them).
