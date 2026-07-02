"""GIF API route handlers — browse/search the deduplicated GIF index."""

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from wumpus_archiver.api.routes._helpers import get_db, get_attachments_path, raise_not_found
from wumpus_archiver.api.schemas import GifListResponse, GifSchema

router = APIRouter()

_SELECT_COLS = """\
    g.id, g.content_hash, g.filename, g.size, g.width, g.height,
    g.local_path, g.url, g.proxy_url, g.usage_count, g.last_used,
    g.channel_id, c.name as channel_name
"""


def _gif_url(request: Request, local_path: str | None) -> str:
    """Build a local URL for the GIF if the file exists on disk."""
    attachments_dir = get_attachments_path(request)
    if attachments_dir and local_path and (attachments_dir / local_path).exists():
        return f"/attachments/{local_path}"
    return ""


def _row_to_gif(request: Request, row: tuple) -> GifSchema:
    """Convert a raw DB row from gif_index to a GifSchema."""
    (
        att_id,
        content_hash,
        filename,
        size,
        width,
        height,
        local_path,
        url,
        proxy_url,
        usage_count,
        last_used,
        channel_id,
        channel_name,
    ) = row

    resolved_url = _gif_url(request, local_path) or url
    return GifSchema(
        id=att_id,
        content_hash=content_hash,
        filename=filename,
        size=size,
        width=width,
        height=height,
        url=resolved_url,
        thumbnail_url=f"/api/gifs/{att_id}/thumb",
        usage_count=usage_count or 1,
        last_used=last_used,
        channel_id=channel_id,
        channel_name=channel_name,
    )


@router.get("/gifs", response_model=GifListResponse)
async def list_gifs(
    request: Request,
    q: str | None = Query(None, description="Search by filename"),
    sort: str = Query("trending", description="Sort: trending, newest, popular"),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    channel_id: int | None = Query(None, description="Filter by origin channel"),
) -> GifListResponse:
    """Browse the deduplicated GIF collection."""
    db = get_db(request)

    conditions = []
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if q:
        conditions.append("g.filename ILIKE :q")
        params["q"] = f"%{q}%"
    if channel_id:
        conditions.append("g.channel_id = :channel_id")
        params["channel_id"] = channel_id

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    if sort == "newest":
        order_by = "g.last_used DESC"
    elif sort == "popular":
        order_by = "g.usage_count DESC"
    else:  # trending — popular + recent
        order_by = "g.usage_count DESC, g.last_used DESC"

    base_sql = f"""\
        SELECT {_SELECT_COLS}
        FROM gif_index g
        LEFT JOIN channels c ON c.id = g.channel_id
        {where_clause}
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """
    count_sql = f"SELECT COUNT(*) FROM gif_index g {where_clause}"

    async with db.session() as session:
        total_result = await session.execute(text(count_sql), params)
        total = total_result.scalar() or 0

        result = await session.execute(text(base_sql), {**params, "limit": limit + 1})
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        gifs = [_row_to_gif(request, r) for r in rows]

        return GifListResponse(
            gifs=gifs,
            total=total,
            has_more=has_more,
            offset=offset,
        )


@router.get("/gifs/trending", response_model=GifListResponse)
async def trending_gifs(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
) -> GifListResponse:
    """Get the most-shared GIFs (by usage count from the gif_index view)."""
    db = get_db(request)

    sql = f"""\
        SELECT {_SELECT_COLS}
        FROM gif_index g
        LEFT JOIN channels c ON c.id = g.channel_id
        ORDER BY g.usage_count DESC, g.last_used DESC
        LIMIT :limit
    """

    async with db.session() as session:
        result = await session.execute(text(sql), {"limit": limit})
        rows = result.all()

        gifs = [_row_to_gif(request, r) for r in rows]

        return GifListResponse(
            gifs=gifs,
            total=len(gifs),
            has_more=False,
            offset=0,
        )


@router.get("/gifs/random", response_model=GifSchema)
async def random_gif(
    request: Request,
    q: str | None = Query(None, description="Optional filename filter"),
) -> GifSchema:
    """Get a random GIF, optionally filtered by filename search."""
    db = get_db(request)

    where_clause = "WHERE g.filename ILIKE :q" if q else ""
    params: dict[str, object] = {}
    if q:
        params["q"] = f"%{q}%"

    sql = f"""\
        SELECT {_SELECT_COLS}
        FROM gif_index g
        LEFT JOIN channels c ON c.id = g.channel_id
        {where_clause}
        ORDER BY random()
        LIMIT 1
    """

    async with db.session() as session:
        result = await session.execute(text(sql), params)
        row = result.first()

        if not row:
            raise_not_found("no GIFs found")

        return _row_to_gif(request, row)


@router.get("/gifs/{gif_id}", response_model=GifSchema)
async def get_gif(
    request: Request,
    gif_id: int,
) -> GifSchema:
    """Get a single GIF by its attachment ID (resolves through content_hash)."""
    db = get_db(request)

    # First find the content_hash for this attachment, then look it up in gif_index.
    hash_sql = text(
        "SELECT content_hash FROM attachments WHERE id = :gif_id "
        "AND content_type = 'image/gif' AND download_status = 'downloaded'"
    )
    sql = f"""\
        SELECT {_SELECT_COLS}
        FROM gif_index g
        LEFT JOIN channels c ON c.id = g.channel_id
        WHERE g.content_hash = :hash
        LIMIT 1
    """

    async with db.session() as session:
        hash_result = await session.execute(hash_sql, {"gif_id": gif_id})
        hash_val = hash_result.scalar()

        if not hash_val:
            raise_not_found(f"GIF {gif_id} not found")

        result = await session.execute(text(sql), {"hash": hash_val})
        row = result.first()

        if not row:
            raise_not_found(f"GIF {gif_id} not found")

        return _row_to_gif(request, row)
