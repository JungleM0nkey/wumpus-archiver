"""Message API route handlers."""

from fastapi import APIRouter, Path, Query, Request

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from wumpus_archiver.api.routes._helpers import get_db, rewrite_attachment_url
from wumpus_archiver.api.schemas import (
    MessageListResponse,
    MessageSchema,
    UserSchema,
)
from wumpus_archiver.models.message import Message

router = APIRouter()


@router.get("/channels/{channel_id}/messages", response_model=MessageListResponse)
async def list_messages(
    request: Request,
    channel_id: int = Path(gt=0),
    before: int | None = Query(None, description="Get messages before this ID"),
    after: int | None = Query(None, description="Get messages after this ID"),
    limit: int = Query(50, ge=1, le=200, description="Number of messages to return"),
) -> MessageListResponse:
    """Get messages from a channel with pagination."""
    db = get_db(request)
    async with db.session() as session:
        query = (
            select(Message)
            .where(Message.channel_id == channel_id)
            .options(
                selectinload(Message.author),
                selectinload(Message.attachments),
                selectinload(Message.reactions),
            )
            .order_by(Message.created_at.asc())
            .limit(limit + 1)
        )

        if before:
            query = query.where(Message.id < before)
        if after:
            query = query.where(Message.id > after)

        result = await session.execute(query)
        messages = list(result.scalars().all())

        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        total_result = await session.execute(
            select(func.count(Message.id)).where(Message.channel_id == channel_id)
        )
        total = total_result.scalar() or 0

        schemas = []
        for msg in messages:
            schema = MessageSchema.model_validate(msg)
            if msg.author:
                author_schema = UserSchema.model_validate(msg.author)
                author_schema.display_name = msg.author.display_name
                schema.author = author_schema
            for att_orm, att_schema in zip(msg.attachments, schema.attachments):
                rewritten = rewrite_attachment_url(
                    request,
                    att_orm.local_path,
                    att_orm.download_status,
                    att_orm.url,
                )
                if rewritten != att_orm.url:
                    att_schema.url = rewritten
                    att_schema.proxy_url = None
            schemas.append(schema)

        return MessageListResponse(
            messages=schemas,
            total=total,
            has_more=has_more,
            before_id=messages[0].id if messages else None,
            after_id=messages[-1].id if messages else None,
        )
