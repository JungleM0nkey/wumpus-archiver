"""Message API route handlers."""

from fastapi import APIRouter, HTTPException, Query

from wumpus_archiver.api.deps import AttachmentsDir, Db
from wumpus_archiver.api.routes._helpers import rewrite_attachment_url
from wumpus_archiver.api.schemas import (
    MessageListResponse,
    MessageReferenceSchema,
    MessageSchema,
    UserSchema,
)
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import Order, Scope

router = APIRouter()

# The channel reader opens at the newest messages and pages back with ``before`` (ADR 0003).
DEFAULT_ORDER = Order.NEWEST_FIRST

# How much of a referenced message's text a reply shows.
REFERENCE_SNIPPET_LENGTH = 120


def _author(user: User) -> UserSchema:
    """A message's author as the API shows it, with their display name."""
    schema = UserSchema.model_validate(user)
    schema.display_name = user.display_name
    return schema


def _snippet(message: Message) -> str:
    """The start of a message's text on one line, cut with an ellipsis."""
    text = " ".join((message.clean_content or message.content).split())
    if len(text) <= REFERENCE_SNIPPET_LENGTH:
        return text
    return text[: REFERENCE_SNIPPET_LENGTH - 1].rstrip() + "…"


def _reference(message: Message) -> MessageReferenceSchema:
    """What a reply shows of the message it refers to."""
    return MessageReferenceSchema(
        id=message.id,
        channel_id=message.channel_id,
        author=_author(message.author) if message.author else None,
        snippet=_snippet(message),
    )


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
    pinned: bool | None = Query(
        None, description="Only pinned messages (true) or only unpinned ones (false)"
    ),
) -> MessageListResponse:
    """Get messages from a channel with pagination.

    ``around`` opens the channel on one message: the page holds it with the messages on
    either side, ``has_more`` says whether older ones remain and ``has_newer`` whether
    newer ones do. It cannot be combined with ``before`` or ``after``.

    ``pinned`` filters the channel's messages, Browse's Pinned tab reading the pinned
    ones; ``total`` counts the filtered messages. It pages with ``before`` and ``after``
    but cannot be combined with ``around``.

    A reply carries ``reference``, what it shows of the message it refers to, read for
    the whole page in one statement.
    """
    if around is not None and (before is not None or after is not None):
        raise HTTPException(status_code=400, detail="around cannot be combined with before/after")
    if around is not None and pinned is not None:
        raise HTTPException(status_code=400, detail="around cannot be combined with pinned")
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
                pinned=pinned,
            )

        referenced = await archive_reads.referenced_messages(session, page.rows)

        schemas = []
        for msg in page.rows:
            schema = MessageSchema.model_validate(msg)
            if msg.author:
                schema.author = _author(msg.author)
            if msg.reference_id is not None and msg.reference_id in referenced:
                schema.reference = _reference(referenced[msg.reference_id])
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
