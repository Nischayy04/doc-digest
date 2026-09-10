import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.clients.document_service import DocumentServiceError
from app.core.config import settings
from app.core.logging import configure_logging
from app.routers import reports

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.service_name)

app.include_router(reports.router, prefix=settings.api_v1_prefix)


@app.exception_handler(DocumentServiceError)
async def document_service_error_handler(request: Request, exc: DocumentServiceError) -> JSONResponse:
    """Handled once, centrally, instead of a try/except repeated in every
    route in app/routers/reports.py. 502 (not 500): this service is fine,
    its upstream (document-service) is what failed."""
    logger.warning("document-service error handling %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """See document-service/app/main.py for why this exists: without it,
    an unexpected error returns a bare plain-text 500 with nothing logged."""
    logger.exception("Unhandled error processing %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}
