import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import configure_logging
from app.routers import documents
from app.services.ollama_client import OllamaServiceError

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.service_name)

app.include_router(documents.router, prefix=settings.api_v1_prefix)


@app.exception_handler(OllamaServiceError)
async def ollama_service_error_handler(request: Request, exc: OllamaServiceError) -> JSONResponse:
    """Mirrors reporting-service's DocumentServiceError handler: 502 (not
    500) because this service is fine, its (local) upstream — Ollama — is
    what failed. Only reachable from the synchronous /ask endpoint;
    summarization in the background pipeline catches this itself and
    degrades to no summary instead of raising."""
    logger.warning("Ollama error handling %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches anything that isn't already an HTTPException (which FastAPI's
    own handler turns into JSON) — an unexpected bug, a DB connectivity
    issue, etc. Without this, Starlette's default is a bare plain-text
    "Internal Server Error" with nothing logged; this logs the full
    traceback server-side and still returns a safe, consistent JSON body
    (no internal details leaked) to the client."""
    logger.exception("Unhandled error processing %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}
