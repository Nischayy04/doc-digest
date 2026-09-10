from fastapi import APIRouter, Depends, Query

from app.clients.document_service import DocumentServiceClient
from app.schemas.reports import ProcessingStatsReport, RecentActivityReport, SummaryReport
from app.services import aggregation

router = APIRouter(prefix="/reports", tags=["reports"])


def get_document_service_client() -> DocumentServiceClient:
    return DocumentServiceClient()


@router.get("/summary", response_model=SummaryReport)
async def get_summary(
    client: DocumentServiceClient = Depends(get_document_service_client),
) -> SummaryReport:
    # DocumentServiceError (document-service unreachable/erroring) isn't
    # caught here — it's handled once, centrally, in main.py's exception
    # handler, instead of a try/except repeated in every route below.
    return await aggregation.build_summary_report(client)


@router.get("/processing-stats", response_model=ProcessingStatsReport)
async def get_processing_stats(
    client: DocumentServiceClient = Depends(get_document_service_client),
) -> ProcessingStatsReport:
    return await aggregation.build_processing_stats_report(client)


@router.get("/recent-activity", response_model=RecentActivityReport)
async def get_recent_activity(
    limit: int = Query(10, ge=1, le=100),
    client: DocumentServiceClient = Depends(get_document_service_client),
) -> RecentActivityReport:
    return await aggregation.build_recent_activity_report(client, limit=limit)
