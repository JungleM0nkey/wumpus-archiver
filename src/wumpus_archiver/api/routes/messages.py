"""Message API route handlers."""

from fastapi import APIRouter, HTTPException, Query

from wumpus_archiver.api.deps import AttachmentsDir, Db
from wumpus_archiver.api.routes._helpers import rewrite_attachment_url
from wumpus_archiver.api.schemas import (
    MessageListResponse,
    MessageSchema,
    UserSchema,
)
from wumpus_archiver.models.message import Message
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import Order, Scope

router = APIRouter()

# The channel reader opens at the newest messages and pages back with ``before`` (ADR 0003).
DEFAULT_ORDER = Order.NEWEST_FIRST


@router.get("/channels/{channel_id}/messages", response_model=MessageListResponse)
async def list_messages(
    db: Db,
    attachments_dir: AttachmentsDir,
    channel_id: int,
    before: int | None = Query(None, description="Get messages before this ID"),
    after: int | None = Query(None, description="Get messages after this ID"),
    limit: int = Query(50, ge=1, le=200, description="Number of messages to return"),
    around: int | None = Query(
        None, description="Get the page around this message ID, including it; alone"
    ),
) -> MessageListResponse:
    """Get messages from a channel with pagination.

    ``around`` opens the channel on one message: the page holds it with the messages on
    either side, ``has_more`` says whether older ones remain and ``has_newer`` whether
    newer ones do. It cannot be combined with ``before`` or ``after``.
    """
    if around is not None and (before is not None or after is not None):
        raise HTTPException(status_code=400, detail="around cannot be combined with before/after")
    has_newer: bool | None = None
    async with db.session() as session:
        page: archive_reads.Page[Message]
        if around is not None:
            page = await archive_reads.messages_around(
                session, Scope(channel=channel_id), order=DEFAULT_ORDER, limit=limit, around=around
            )
            has_newer = page.has_newer
        else:
            page = await archive_reads.messages(
                session,
                Scope(channel=channel_id),
                order=DEFAULT_ORDER,
                limit=limit,
                before=before,
                after=after,
            )

        schemas = []
        for msg in page.rows:
            schema = MessageSchema.model_validate(msg)
            if msg.author:
                author_schema = UserSchema.model_validate(msg.author)
                author_schema.display_name = msg.author.display_name
                schema.author = author_schema
            for att_orm, att_schema in zip(msg.attachments, schema.attachments):
                rewritten = rewrite_attachment_url(
                    attachments_dir,
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
            total=page.total,
            has_more=page.has_more,
            before_id=page.oldest_id,
            after_id=page.newest_id,
            has_newer=has_newer,
        )
