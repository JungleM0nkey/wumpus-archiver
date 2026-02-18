"""Search API route handlers."""

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from wumpus_archiver.api.routes._helpers import get_db, rewrite_attachment_url
from wumpus_archiver.api.schemas import (
    MessageSchema,
    SearchResponse,
    SearchResultSchema,
    UserSchema,
)
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.message import Message

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search_messages(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    guild_id: int | None = Query(None, description="Filter by guild"),
    channel_id: int | None = Query(None, description="Filter by channel"),
    author_id: int | None = Query(None, description="Filter by author"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
) -> SearchResponse:
    """Search messages by content."""
    db = get_db(request)
    async with db.session() as session:
        query = (
            select(Message)
            .options(
                selectinload(Message.author),
                selectinload(Message.attachments),
                selectinload(Message.reactions),
            )
            .where(Message.content.ilike(f"%{q}%"))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )

        if channel_id:
            query = query.where(Message.channel_id == channel_id)
        elif guild_id:
            query = query.where(
                Message.channel_id.in_(
                    select(Channel.id).where(Channel.guild_id == guild_id)
                )
            )
        if author_id:
            query = query.where(Message.author_id == author_id)

        result = await session.execute(query)
        messages = list(result.scalars().all())

        channel_ids = {m.channel_id for m in messages}
        ch_result = await session.execute(
            select(Channel).where(Channel.id.in_(channel_ids))
        )
        channel_map = {ch.id: ch.name for ch in ch_result.scalars().all()}

        count_query = select(func.count(Message.id)).where(
            Message.content.ilike(f"%{q}%")
        )
        if channel_id:
            count_query = count_query.where(Message.channel_id == channel_id)
        elif guild_id:
            count_query = count_query.where(
                Message.channel_id.in_(
                    select(Channel.id).where(Channel.guild_id == guild_id)
                )
            )
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        results = []
        for msg in messages:
            msg_schema = MessageSchema.model_validate(msg)
            if msg.author:
                author_schema = UserSchema.model_validate(msg.author)
                author_schema.display_name = msg.author.display_name
                msg_schema.author = author_schema
            for att_orm, att_schema in zip(msg.attachments, msg_schema.attachments):
                rewritten = rewrite_attachment_url(
                    request,
                    att_orm.local_path,
                    att_orm.download_status,
                    att_orm.url,
                )
                if rewritten != att_orm.url:
                    att_schema.url = rewritten
                    att_schema.proxy_url = None

            results.append(
                SearchResultSchema(
                    message=msg_schema,
                    channel_name=channel_map.get(msg.channel_id, "unknown"),
                )
            )

        return SearchResponse(results=results, total=total, query=q)
