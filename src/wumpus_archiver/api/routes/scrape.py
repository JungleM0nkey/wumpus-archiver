"""Scrape control panel API route handlers."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from wumpus_archiver.api.schemas import (
    AnalyzeChannelSchema,
    AnalyzeResponse,
    ScrapeableChannelSchema,
    ScrapeableChannelsResponse,
    ScrapeHistoryResponse,
    ScrapeJobSchema,
    ScrapeProgressSchema,
    ScrapeStartRequest,
    ScrapeStatusResponse,
)
from wumpus_archiver.api.auth import require_auth
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild as GuildModel

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

    scope = "channels" if job.channel_ids else "guild"

    return ScrapeJobSchema(
        id=job.id,
        guild_id=job.guild_id,
        channel_ids=job.channel_ids,
        scope=scope,
        status=job.status.value,
        progress=ScrapeProgressSchema(
            current_channel=job.progress.current_channel,
            channels_done=job.progress.channels_done,
            channels_total=job.progress.channels_total,
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
async def scrape_start(
    request: Request, body: ScrapeStartRequest, _: None = Depends(require_auth)
) -> JSONResponse:
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

    guild_id = int(body.guild_id)
    channel_ids = [int(c) for c in body.channel_ids] if body.channel_ids else None
    job = manager.start_scrape(guild_id, token, channel_ids=channel_ids)
    return JSONResponse(
        status_code=202,
        content={"job": _job_to_schema(job).model_dump()},
    )


@router.post("/scrape/cancel")
async def scrape_cancel(request: Request, _: None = Depends(require_auth)) -> JSONResponse:
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


# Discord channel type helpers
_CHANNEL_TYPE_NAMES: dict[int, str] = {
    0: "Text",
    2: "Voice",
    4: "Category",
    5: "Announcement",
    11: "Public Thread",
    12: "Private Thread",
    13: "Stage",
    15: "Forum",
}


@router.get(
    "/scrape/guilds/{guild_id}/channels",
    response_model=ScrapeableChannelsResponse,
)
async def list_scrapeable_channels(
    request: Request,
    guild_id: int = Path(gt=0),
) -> JSONResponse:
    """List channels available for scraping.

    Tries to fetch live channels from Discord API first, merged with DB data
    for archival metadata (message counts, scraped status). Falls back to
    DB-only if no token is configured or the API call fails.
    """
    manager = _get_scrape_manager(request)
    db = request.app.state.database
    token = getattr(request.app.state, "discord_token", None)

    # Fetch DB channels and guild info
    async with db.session() as session:
        result = await session.execute(
            select(Channel)
            .where(Channel.guild_id == guild_id)
            .order_by(Channel.position)
        )
        db_channels = list(result.scalars().all())

        guild_result = await session.execute(
            select(GuildModel).where(GuildModel.id == guild_id)
        )
        guild = guild_result.scalar_one_or_none()
        guild_name = guild.name if guild else f"Guild {guild_id}"

    # Build DB lookup: channel_id -> Channel
    db_lookup: dict[int, Channel] = {ch.id: ch for ch in db_channels}

    # Build category lookup from DB channels
    category_names: dict[int, str] = {}
    for ch in db_channels:
        if ch.type == 4:  # GUILD_CATEGORY
            category_names[ch.id] = ch.name

    # Try fetching live channels from Discord
    live_channels: list[dict] | None = None
    if token:
        live_channels = await manager.fetch_live_channels(token, guild_id)

    if live_channels is not None:
        # Merge live data with DB metadata
        # Update category lookup with live data
        for lc in live_channels:
            if lc.get("type") == 4:
                category_names[int(lc["id"])] = lc["name"]

        channels: list[ScrapeableChannelSchema] = []
        for lc in live_channels:
            ch_type = lc.get("type", 0)
            if ch_type == 4:  # Skip categories
                continue

            ch_id = int(lc["id"])
            db_ch = db_lookup.get(ch_id)
            parent_id = int(lc["parent_id"]) if lc.get("parent_id") else None

            channels.append(
                ScrapeableChannelSchema(
                    id=ch_id,
                    name=lc.get("name", "unknown"),
                    type=ch_type,
                    type_name=_CHANNEL_TYPE_NAMES.get(ch_type, f"Type {ch_type}"),
                    parent_name=category_names.get(parent_id) if parent_id else None,
                    position=lc.get("position", 0),
                    already_scraped=db_ch.message_count > 0 if db_ch else False,
                    archived_message_count=db_ch.message_count if db_ch else 0,
                )
            )

        channels.sort(key=lambda c: c.position)
    else:
        # Fallback: DB-only (no token or API call failed)
        if not db_channels:
            return JSONResponse(
                status_code=404,
                content={
                    "error": f"No channels found for guild {guild_id}. "
                    "Scrape the guild first or configure a bot token."
                },
            )

        channels = []
        for ch in db_channels:
            if ch.type == 4:
                continue

            channels.append(
                ScrapeableChannelSchema(
                    id=ch.id,
                    name=ch.name,
                    type=ch.type,
                    type_name=_CHANNEL_TYPE_NAMES.get(ch.type, f"Type {ch.type}"),
                    parent_name=category_names.get(ch.parent_id) if ch.parent_id else None,
                    position=ch.position,
                    already_scraped=ch.message_count > 0,
                    archived_message_count=ch.message_count,
                )
            )

    return JSONResponse(
        content=ScrapeableChannelsResponse(
            guild_id=guild_id,
            guild_name=guild_name,
            channels=channels,
            total=len(channels),
        ).model_dump(),
    )


@router.get("/scrape/guilds/{guild_id}/analyze")
async def analyze_guild(
    request: Request,
    guild_id: int = Path(gt=0),
) -> JSONResponse:
    """Analyze a guild to find new/updated channels before scraping.

    Compares live Discord channel data with the local archive to identify
    what needs to be scraped. Uses last_message_id comparison to detect
    channels with new messages.
    """
    manager = _get_scrape_manager(request)
    db = request.app.state.database
    token = getattr(request.app.state, "discord_token", None)

    if not token:
        return JSONResponse(
            status_code=400,
            content={"error": "No Discord bot token configured. Cannot analyze live guild data."},
        )

    # Fetch live channels from Discord
    live_channels = await manager.fetch_live_channels(token, guild_id)
    if live_channels is None:
        return JSONResponse(
            status_code=502,
            content={"error": "Failed to fetch channels from Discord API."},
        )

    # Fetch DB state
    async with db.session() as session:
        result = await session.execute(
            select(Channel).where(Channel.guild_id == guild_id)
        )
        db_channels = list(result.scalars().all())

        guild_result = await session.execute(
            select(GuildModel).where(GuildModel.id == guild_id)
        )
        guild = guild_result.scalar_one_or_none()
        guild_name = guild.name if guild else f"Guild {guild_id}"

    db_lookup: dict[int, Channel] = {ch.id: ch for ch in db_channels}

    # Build category lookup from live data
    category_names: dict[int, str] = {}
    for lc in live_channels:
        if lc.get("type") == 4:
            category_names[int(lc["id"])] = lc["name"]

    # Compare live vs DB
    analyzed: list[AnalyzeChannelSchema] = []
    summary: dict[str, int] = {"new": 0, "has_new_messages": 0, "up_to_date": 0, "never_scraped": 0}

    for lc in live_channels:
        ch_type = lc.get("type", 0)
        if ch_type == 4:  # Skip categories
            continue

        ch_id = int(lc["id"])
        db_ch = db_lookup.get(ch_id)
        parent_id = int(lc["parent_id"]) if lc.get("parent_id") else None
        live_last_msg = lc.get("last_message_id")

        # Determine status
        if db_ch is None:
            status = "new"
        elif db_ch.message_count == 0:
            status = "never_scraped"
        elif live_last_msg and db_ch.last_message_id and int(live_last_msg) > db_ch.last_message_id:
            status = "has_new_messages"
        else:
            status = "up_to_date"

        summary[status] += 1

        analyzed.append(
            AnalyzeChannelSchema(
                id=ch_id,
                name=lc.get("name", "unknown"),
                type=ch_type,
                type_name=_CHANNEL_TYPE_NAMES.get(ch_type, f"Type {ch_type}"),
                parent_name=category_names.get(parent_id) if parent_id else None,
                position=lc.get("position", 0),
                status=status,
                archived_message_count=db_ch.message_count if db_ch else 0,
                last_scraped_at=db_ch.last_scraped_at.isoformat() if db_ch and db_ch.last_scraped_at else None,
            )
        )

    analyzed.sort(key=lambda c: c.position)

    return JSONResponse(
        content=AnalyzeResponse(
            guild_id=guild_id,
            guild_name=guild_name,
            channels=analyzed,
            summary=summary,
        ).model_dump(),
    )
