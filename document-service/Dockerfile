# ---- builder: resolve and install Python dependencies ----
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- runtime: slim image, non-root user, no build tooling ----
FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# Create the upload storage dir with correct ownership *before* the named
# volume (docker-compose.yml) is ever mounted here — on first use, Docker
# copies an image directory's existing content/ownership into a brand-new
# named volume, which is what lets the non-root user write to it later.
RUN mkdir -p storage && chown -R appuser:appuser /app

USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH

EXPOSE 8001

# Apply any pending migrations, then start the API. Safe to run on every
# startup — alembic upgrade head is a no-op if the DB is already current.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001"]
