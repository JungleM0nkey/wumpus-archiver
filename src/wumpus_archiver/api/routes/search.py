"""Search API route handlers."""

from fastapi import APIRouter, Query

from wumpus_archiver.api.deps import AttachmentsDir, Db
from wumpus_archiver.api.routes._helpers import rewrite_attachment_url
from wumpus_archiver.api.schemas import (
    MessageSchema,
    SearchResponse,
    SearchResultSchema,
    UserSchema,
)
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import Order, Scope

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search_messages(
    db: Db,
    attachments_dir: AttachmentsDir,
    q: str = Query(..., min_length=1, description="Search query"),
    guild_id: int | None = Query(None, description="Filter by guild"),
    channel_id: int | None = Query(None, description="Filter by channel"),
    author_id: int | None = Query(None, description="Filter by author"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
) -> SearchResponse:
    """Search messages by content."""
    async with db.session() as session:
        page = await archive_reads.messages(
            session,
            Scope(guild=guild_id, channel=channel_id, author=author_id),
            order=Order.NEWEST_FIRST,
            limit=limit,
            text=q,
        )

        results = []
        for msg in page.rows:
            msg_schema = MessageSchema.model_validate(msg)
            if msg.author:
                author_schema = UserSchema.model_validate(msg.author)
                author_schema.display_name = msg.author.display_name
                msg_schema.author = author_schema
            for att_orm, att_schema in zip(msg.attachments, msg_schema.attachments):
                rewritten = rewrite_attachment_url(
                    attachments_dir,
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
                    channel_name=msg.channel.name if msg.channel else "unknown",
                )
            )

        return SearchResponse(results=results, total=page.total, query=q)
