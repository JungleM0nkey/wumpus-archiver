"""Scrape control panel API route handlers."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from wumpus_archiver.api.schemas import (
    ScrapeHistoryResponse,
    ScrapeJobSchema,
    ScrapeProgressSchema,
    ScrapeStartRequest,
    ScrapeStatusResponse,
)

router = APIRouter()


def _get_scrape_manager(request: Request):  # type: ignore[no-untyped-def]
    """Get the scrape job manager from app state."""
    return request.app.state.scrape_manager


def _job_to_schema(job) -> ScrapeJobSchema:  # type: ignore[no-untyped-def]
    """Convert a ScrapeJob model to a response schema."""
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
async def scrape_status(request: Request) -> ScrapeStatusResponse:
    """Get current scrape job status."""
    manager = _get_scrape_manager(request)
    has_token = getattr(request.app.state, "discord_token", None) is not None

    if manager.current_job is not None:
        return ScrapeStatusResponse(
            busy=manager.is_busy,
            current_job=_job_to_schema(manager.current_job),
            has_token=has_token,
        )

    return ScrapeStatusResponse(busy=False, has_token=has_token)


@router.post("/scrape/start")
async def scrape_start(request: Request, body: ScrapeStartRequest) -> JSONResponse:
    """Start a new scrape job."""
    manager = _get_scrape_manager(request)
    token = getattr(request.app.state, "discord_token", None)

    if not token:
        return JSONResponse(
            status_code=400,
            content={
                "error": "No Discord bot token configured. "
                "Set DISCORD_BOT_TOKEN in .env or environment."
            },
        )

    if manager.is_busy:
        return JSONResponse(
            status_code=409,
            content={"error": "A scrape job is already running"},
        )

    job = manager.start_scrape(body.guild_id, token)
    return JSONResponse(
        status_code=202,
        content={"job": _job_to_schema(job).model_dump()},
    )


@router.post("/scrape/cancel")
async def scrape_cancel(request: Request) -> JSONResponse:
    """Cancel the current scrape job."""
    manager = _get_scrape_manager(request)

    if manager.cancel():
        return JSONResponse(content={"message": "Cancellation requested"})

    return JSONResponse(
        status_code=404,
        content={"error": "No running job to cancel"},
    )


@router.get("/scrape/history", response_model=ScrapeHistoryResponse)
async def scrape_history(request: Request) -> ScrapeHistoryResponse:
    """Get scrape job history."""
    manager = _get_scrape_manager(request)
    return ScrapeHistoryResponse(
        jobs=[_job_to_schema(j) for j in manager.history],
    )
