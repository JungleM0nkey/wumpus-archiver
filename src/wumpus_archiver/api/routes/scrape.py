"""Scrape control API route handlers."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from wumpus_archiver.api.auth import require_api_token
from wumpus_archiver.api.deps import ApiAuthToken, Scrape
from wumpus_archiver.api.schemas import (
    ScrapeHistoryResponse,
    ScrapeJobSchema,
    ScrapeProgressSchema,
    ScrapeStartRequest,
    ScrapeStatusResponse,
)
from wumpus_archiver.api.scrape_control import ScrapeJob

router = APIRouter()

READ_ONLY_ERROR = (
    "Scrape control is read-only: no Discord bot token was configured when the server started."
)


def _job_to_schema(job: ScrapeJob) -> ScrapeJobSchema:
    """Convert a ScrapeJob to a response schema."""
    duration: float | None = None
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()
    elif job.started_at:
        duration = (datetime.now(UTC) - job.started_at).total_seconds()

    return ScrapeJobSchema(
        id=job.id,
        guild_id=job.guild_id,
        status=job.status.value,
        progress=ScrapeProgressSchema(
            current_channel=job.progress.current_channel,
            channels_done=job.progress.channels_done,
            messages_scraped=job.progress.messages_scraped,
            attachments_found=job.progress.attachments_found,
            errors=job.progress.errors,
        ),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        result=job.result,
        error_message=job.error_message,
        duration_seconds=round(duration, 1) if duration is not None else None,
    )


@router.get("/scrape/status", response_model=ScrapeStatusResponse)
async def scrape_status(scrape: Scrape, api_auth_token: ApiAuthToken) -> ScrapeStatusResponse:
    """Get current scrape job status."""
    control_enabled = api_auth_token is not None
    if scrape.current_job is not None:
        return ScrapeStatusResponse(
            busy=scrape.is_busy,
            current_job=_job_to_schema(scrape.current_job),
            has_token=scrape.configured,
            control_enabled=control_enabled,
        )

    return ScrapeStatusResponse(
        busy=False, has_token=scrape.configured, control_enabled=control_enabled
    )


@router.post("/scrape/start", dependencies=[Depends(require_api_token)])
async def scrape_start(scrape: Scrape, body: ScrapeStartRequest) -> JSONResponse:
    """Start a new scrape job (requires the API bearer token)."""
    if not scrape.configured:
        return JSONResponse(status_code=400, content={"error": READ_ONLY_ERROR})

    if scrape.is_busy:
        return JSONResponse(
            status_code=409,
            content={"error": "A scrape job is already running"},
        )

    job = scrape.start_scrape(body.guild_id)
    return JSONResponse(
        status_code=202,
        content={"job": _job_to_schema(job).model_dump()},
    )


@router.post("/scrape/cancel", dependencies=[Depends(require_api_token)])
async def scrape_cancel(scrape: Scrape) -> JSONResponse:
    """Cancel the current scrape job (requires the API bearer token)."""
    if scrape.cancel():
        return JSONResponse(content={"message": "Cancellation requested"})

    return JSONResponse(
        status_code=404,
        content={"error": "No running job to cancel"},
    )


@router.get("/scrape/history", response_model=ScrapeHistoryResponse)
async def scrape_history(scrape: Scrape) -> ScrapeHistoryResponse:
    """Get scrape job history."""
    return ScrapeHistoryResponse(jobs=[_job_to_schema(j) for j in scrape.history])
