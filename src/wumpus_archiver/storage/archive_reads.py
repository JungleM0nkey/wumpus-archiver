"""Archive reads: the named reads of the archive, each over a scope.

See ``docs/adr/0002`` and ``docs/adr/0003``. Every read takes the ``AsyncSession`` its
caller opened and never writes, commits, flushes or closes it. This module imports the
models only, never FastAPI or the API schemas.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.message import Message


class MediaKind(Enum):
    """A kind of attachment the portal and the downloader select by content type."""

    IMAGE = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/avif")
    GIF = ("image/gif",)
    VIDEO = ("video/mp4", "video/webm", "video/quicktime")

    @property
    def content_types(self) -> tuple[str, ...]:
        """The content types an attachment of this kind may carry."""
        types: tuple[str, ...] = self.value
        return types


def escape_like(value: str, escape: str = "\\") -> str:
    """Escape SQL ``LIKE`` wildcards so user input matches literally.

    The escape character is escaped first, then ``%`` and ``_``. The caller must
    pass the same escape character to the ``LIKE`` clause (``ESCAPE '\\'`` in raw
    SQL or ``escape="\\\\"`` in SQLAlchemy ``like``/``ilike``).

    Args:
        value: Raw user-supplied search text
        escape: Escape character used by the ``LIKE`` clause

    Returns:
        The value with ``escape``, ``%`` and ``_`` each prefixed by ``escape``
    """
    return (
        value.replace(escape, escape + escape).replace("%", escape + "%").replace("_", escape + "_")
    )


@dataclass(frozen=True)
class Scope:
    """Which part of the archive a read covers.

    Guild, channel and author are all optional and all applied together, so a channel
    outside the guild yields nothing. An empty scope is the whole archive.
    """

    guild: int | None = None
    channel: int | None = None
    author: int | None = None


@dataclass(frozen=True)
class Page[T]:
    """One page of a paged read.

    ``total`` is the count of everything the read matches, ignoring paging. For message
    pages, ``oldest_id`` and ``newest_id`` are the ids to pass as ``before`` and ``after``.
    """

    rows: list[T]
    total: int
    has_more: bool
    oldest_id: int | None = None
    newest_id: int | None = None


class Order(StrEnum):
    """The order messages are returned in."""

    OLDEST_FIRST = "oldest"
    NEWEST_FIRST = "newest"


class Has(StrEnum):
    """Something a message carries."""

    FILE = "file"
    IMAGE = "image"
    VIDEO = "video"
    LINK = "link"


def _naive_utc(value: datetime) -> datetime:
    """The archive stores naive UTC; convert an aware datetime to that."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _message_scope(scope: Scope) -> list[ColumnElement[bool]]:
    """The predicates that confine messages to a scope."""
    predicates: list[ColumnElement[bool]] = []
    if scope.guild is not None:
        predicates.append(
            Message.channel_id.in_(select(Channel.id).where(Channel.guild_id == scope.guild))
        )
    if scope.channel is not None:
        predicates.append(Message.channel_id == scope.channel)
    if scope.author is not None:
        predicates.append(Message.author_id == scope.author)
    return predicates


def _has(has: Has) -> ColumnElement[bool]:
    """The predicate for a message carrying ``has``."""
    if has is Has.LINK:
        return or_(Message.content.contains("http://"), Message.content.contains("https://"))
    carried = Attachment.message_id == Message.id
    if has is Has.IMAGE:
        carried = and_(carried, Attachment.content_type.in_(MediaKind.IMAGE.content_types))
    elif has is Has.VIDEO:
        carried = and_(carried, Attachment.content_type.in_(MediaKind.VIDEO.content_types))
    return exists().where(carried)


async def _page(
    session: AsyncSession,
    rows: Select[Any],
    where: Sequence[ColumnElement[bool]],
    count_from: Any,
    *,
    limit: int,
    offset: int = 0,
    paging: Sequence[ColumnElement[bool]] = (),
) -> tuple[list[Any], int, bool]:
    """Fetch one page of ``rows`` and the total of everything ``where`` matches.

    Over-fetches one row past ``limit`` for ``has_more``. The ``count(*)`` over
    ``count_from`` uses the same ``where`` as the rows (``paging`` narrows the rows
    only) and is skipped when the first page is already the whole result.

    Returns:
        The rows of the page, the total and whether more rows follow
    """
    result = await session.execute(rows.where(*where, *paging).offset(offset).limit(limit + 1))
    fetched = list(result.all())
    has_more = len(fetched) > limit
    fetched = fetched[:limit]
    if offset == 0 and not paging and not has_more:
        return fetched, len(fetched), False
    counted = await session.execute(select(func.count()).select_from(count_from).where(*where))
    return fetched, int(counted.scalar_one()), has_more


async def messages(
    session: AsyncSession,
    scope: Scope,
    *,
    order: Order,
    limit: int,
    before: int | None = None,
    after: int | None = None,
    text: str | None = None,
    has: Has | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Page[Message]:
    """Messages in scope, with their channel, author, attachments and reactions loaded.

    A cursor is a message id. ``before`` returns the page adjacent to it on the older
    side and ``after`` the page adjacent on the newer side, in ``order`` either way;
    with both, the page is the one next to ``before`` that is still newer than
    ``after``. An unknown cursor is ignored. ``text`` matches the content
    case-insensitively with LIKE wildcards taken literally. ``since`` is inclusive and
    ``until`` exclusive; aware datetimes are converted to naive UTC.
    """
    where = _message_scope(scope)
    if text is not None:
        where.append(Message.content.ilike(f"%{escape_like(text)}%", escape="\\"))
    if has is not None:
        where.append(_has(has))
    if since is not None:
        where.append(Message.created_at >= _naive_utc(since))
    if until is not None:
        where.append(Message.created_at < _naive_utc(until))

    paging: list[ColumnElement[bool]] = []
    older_anchor = await _anchor(session, before)
    newer_anchor = await _anchor(session, after)
    if older_anchor is not None:
        at, at_id = older_anchor
        paging.append(
            or_(Message.created_at < at, and_(Message.created_at == at, Message.id < at_id))
        )
    if newer_anchor is not None:
        at, at_id = newer_anchor
        paging.append(
            or_(Message.created_at > at, and_(Message.created_at == at, Message.id > at_id))
        )

    # Walk away from the cursor: towards older messages from ``before`` or for a
    # newest-first first page, towards newer ones otherwise. Then return in ``order``.
    if older_anchor is not None:
        walk_newest_first = True
    elif newer_anchor is not None:
        walk_newest_first = False
    else:
        walk_newest_first = order is Order.NEWEST_FIRST
    ordering = (
        (Message.created_at.desc(), Message.id.desc())
        if walk_newest_first
        else (Message.created_at.asc(), Message.id.asc())
    )
    rows = (
        select(Message)
        .options(
            joinedload(Message.channel),
            selectinload(Message.author),
            selectinload(Message.attachments),
            selectinload(Message.reactions),
        )
        .order_by(*ordering)
    )
    fetched, total, has_more = await _page(
        session, rows, where, Message, limit=limit, paging=paging
    )
    page: list[Message] = [row[0] for row in fetched]
    if walk_newest_first != (order is Order.NEWEST_FIRST):
        page.reverse()
    ids = [message.id for message in page]
    if order is Order.NEWEST_FIRST:
        ids.reverse()
    return Page(
        rows=page,
        total=total,
        has_more=has_more,
        oldest_id=ids[0] if ids else None,
        newest_id=ids[-1] if ids else None,
    )


async def _anchor(session: AsyncSession, cursor: int | None) -> tuple[datetime, int] | None:
    """The ``(created_at, id)`` of a cursor message, or ``None`` if there is none."""
    if cursor is None:
        return None
    result = await session.execute(
        select(Message.created_at, Message.id).where(Message.id == cursor)
    )
    row = result.first()
    return (row[0], row[1]) if row else None
