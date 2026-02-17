"""Data source switching API."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from wumpus_archiver.api.auth import require_auth
from wumpus_archiver.api.schemas import (
    DataSourceInfo,
    DataSourceResponse,
    DataSourceSetRequest,
)
from wumpus_archiver.storage.database import DatabaseRegistry

router = APIRouter()


def _get_registry(request: Request) -> DatabaseRegistry:
    """Get the database registry from app state."""
    return request.app.state.db_registry  # type: ignore[no-any-return]


@router.get("/datasource", response_model=DataSourceResponse)
async def get_datasource(request: Request) -> DataSourceResponse:
    """Get current data source configuration."""
    registry = _get_registry(request)
    sources: dict[str, DataSourceInfo] = {}
    for name in registry.available_sources:
        url = registry.source_urls.get(name, "")
        if name == "sqlite":
            # Show the file path for SQLite, check if file exists
            path = url.replace("sqlite+aiosqlite:///", "")
            available = Path(path).exists() and Path(path).stat().st_size > 0
            sources[name] = DataSourceInfo(label="SQLite", detail=path, available=available)
        else:
            # For PostgreSQL, show host/db but mask password
            sources[name] = DataSourceInfo(label="PostgreSQL", detail=_mask_pg_url(url))
    return DataSourceResponse(active=registry.active, sources=sources)


@router.put("/datasource")
async def set_datasource(
    request: Request, body: DataSourceSetRequest, _: None = Depends(require_auth)
) -> JSONResponse:
    """Switch the active data source."""
    registry = _get_registry(request)
    try:
        await registry.set_active_safe(body.active)
    except KeyError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return JSONResponse(content={"active": registry.active})


def _mask_pg_url(url: str) -> str:
    """Mask password in PostgreSQL URL for display."""
    # postgresql+asyncpg://user:pass@host:port/db -> postgresql+asyncpg://user:***@host:port/db
    if "@" in url and ":" in url.split("@")[0]:
        prefix, rest = url.split("@", 1)
        parts = prefix.rsplit(":", 1)
        return f"{parts[0]}:***@{rest}"
    return url
