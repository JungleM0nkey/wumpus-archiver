"""Data transfer API route handlers."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from wumpus_archiver.api.schemas import TransferStatusSchema
from wumpus_archiver.api.transfer_manager import TransferManager

router = APIRouter()


def _get_transfer_manager(request: Request) -> TransferManager:
    return request.app.state.transfer_manager


def _job_to_schema(job) -> dict:
    """Convert a TransferJob to a dict matching TransferStatusSchema."""
    return TransferStatusSchema(
        status=job.status,
        current_table=job.current_table,
        tables_done=job.tables_done,
        tables_total=job.tables_total,
        rows_transferred=job.rows_transferred,
        total_rows=job.total_rows,
        error=job.error,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    ).model_dump()


@router.post("/transfer/start")
async def transfer_start(request: Request) -> JSONResponse:
    """Start a data transfer from SQLite to PostgreSQL."""
    manager = _get_transfer_manager(request)
    registry = request.app.state.db_registry

    if len(registry.available_sources) < 2:
        return JSONResponse(
            status_code=400,
            content={"error": "Need at least two data sources configured to transfer."},
        )

    if manager.is_busy:
        return JSONResponse(
            status_code=409,
            content={"error": "A transfer is already running"},
        )

    try:
        job = manager.start_transfer("sqlite", "postgres")
        return JSONResponse(status_code=202, content=_job_to_schema(job))
    except KeyError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.get("/transfer/status")
async def transfer_status(request: Request) -> JSONResponse:
    """Get current transfer job status."""
    manager = _get_transfer_manager(request)
    job = manager.current_job

    if job is None:
        return JSONResponse(
            content=TransferStatusSchema(
                status="idle",
                current_table="",
                tables_done=0,
                tables_total=0,
                rows_transferred=0,
                total_rows=0,
            ).model_dump()
        )

    return JSONResponse(content=_job_to_schema(job))


@router.post("/transfer/cancel")
async def transfer_cancel(request: Request) -> JSONResponse:
    """Cancel the current transfer."""
    manager = _get_transfer_manager(request)

    if manager.cancel():
        return JSONResponse(content={"message": "Cancellation requested"})

    return JSONResponse(
        status_code=404,
        content={"error": "No running transfer to cancel"},
    )
