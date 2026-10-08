"""Search API route handlers."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from wumpus_archiver.api.deps import AttachmentsDir, Db
from wumpus_archiver.api.routes._helpers import rewrite_attachment_url
from wumpus_archiver.api.schemas import (
    MessageSchema,
    SearchAuthorFacetSchema,
    SearchChannelFacetSchema,
    SearchFacetsSchema,
    SearchMonthFacetSchema,
    SearchResponse,
    SearchResultSchema,
    UserSchema,
)
from wumpus_archiver.api.search_text import highlight, search_terms
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import Has, Order, Scope

router = APIRouter()

FACET_LIMIT = 10
"""How many channels and authors each facet lists, the busiest first."""


def _start_of(day: dt.date | None) -> dt.datetime | None:
    """Midnight UTC at the start of ``day``, as the archive stores times (naive UTC)."""
    return None if day is None else dt.datetime.combine(day, dt.time())


@router.get("/search", response_model=SearchResponse)
async def search_messages(
    db: Db,
    attachments_dir: AttachmentsDir,
    q: str | None = Query(
        None,
        min_length=1,
        description=(
            "Search terms, every one of which a message must contain; a double-quoted "
            "phrase is one term. May be left out when another filter is given"
        ),
    ),
    guild_id: int | None = Query(None, description="Filter by guild"),
    channel_id: int | None = Query(None, description="Filter by channel"),
    author_id: int | None = Query(None, description="Filter by author"),
    has: Annotated[
        Has | None, Query(description="Only messages carrying a file, image, video or link")
    ] = None,
    after: Annotated[
        dt.date | None,
        Query(description="Only messages on or after this day (inclusive, from 00:00 UTC)"),
    ] = None,
    before: Annotated[
        dt.date | None,
        Query(description="Only messages before this day (exclusive, up to 00:00 UTC)"),
    ] = None,
    sort: Annotated[Order, Query(description="newest or oldest first")] = Order.NEWEST_FIRST,
    cursor: Annotated[
        int | None,
        Query(description="The last result of the previous page; the page after it in sort"),
    ] = None,
    facets: Annotated[
        bool, Query(description="Also count the matches per channel, author and month")
    ] = False,
    limit: int = Query(50, ge=1, le=100, description="Max results"),
) -> SearchResponse:
    """Messages in scope whose content contains every term of ``q``, newest first.

    ``after`` and ``before`` are days in UTC: ``after`` is inclusive and ``before``
    exclusive, as the archive read's ``since`` and ``until`` are, so
    ``after=2024-05-01&before=2024-06-01`` is May. ``has`` keeps messages carrying a
    file of any kind, an image, a video or a link. ``sort=oldest`` reverses the order.
    Each result's ``highlight`` is the escaped snippet around its first match, with the
    terms marked. ``facets=true`` adds the matches' counts per channel and author (the
    busiest ten) and per month, for the same filters.

    Without ``q`` the read is every message the other filters keep, so one of
    ``author_id``, ``channel_id``, ``has``, ``after`` or ``before`` is then required (an
    id of 0 is no filter, as for every id here; a guild alone is not enough).
    """
    terms = search_terms(q)
    if not terms and not (author_id or channel_id or has or after or before):
        raise HTTPException(
            status_code=422, detail="q is required unless a channel, author, has or date is given"
        )
    scope = Scope(guild=guild_id or None, channel=channel_id or None, author=author_id or None)
    since, until = _start_of(after), _start_of(before)
    newest_first = sort is Order.NEWEST_FIRST
    async with db.session() as session:
        page = await archive_reads.messages(
            session,
            scope,
            order=sort,
            limit=limit,
            before=cursor if newest_first else None,
            after=None if newest_first else cursor,
            terms=terms,
            has=has,
            since=since,
            until=until,
            with_channel=True,
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
                    highlight=highlight(msg.content, terms),
                )
            )

        facets_schema: SearchFacetsSchema | None = None
        if facets:
            counted = await archive_reads.search_facets(
                session,
                scope,
                limit=FACET_LIMIT,
                terms=terms,
                has=has,
                since=since,
                until=until,
            )
            facets_schema = SearchFacetsSchema(
                channels=[
                    SearchChannelFacetSchema(id=c.channel_id, name=c.name, count=c.messages)
                    for c in counted.channels
                ],
                authors=[
                    SearchAuthorFacetSchema(
                        id=a.user.id,
                        username=a.user.username,
                        display_name=a.user.display_name,
                        avatar_url=a.user.avatar_url,
                        count=a.messages,
                    )
                    for a in counted.authors
                ],
                months=[
                    SearchMonthFacetSchema(start=m.start, count=m.messages) for m in counted.months
                ],
            )

        return SearchResponse(
            results=results,
            total=page.total,
            query=q,
            has_more=page.has_more,
            facets=facets_schema,
        )
