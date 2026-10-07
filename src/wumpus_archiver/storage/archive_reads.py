"""Archive reads: the named reads of the archive, each over a scope.

See ``docs/adr/0002`` and ``docs/adr/0003``. Every read takes the ``AsyncSession`` its
caller opened and never writes, commits, flushes or closes it. This module imports the
models only, never FastAPI or the API schemas.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum, StrEnum
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, extract, func, join, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User


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
class GuildCounts:
    """How many channels a guild has and how many messages they hold, counted live."""

    channels: int = 0
    messages: int = 0


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


@dataclass(frozen=True)
class AttachmentRow:
    """An attachment with the message context the gallery shows beside it."""

    attachment: Attachment
    created_at: datetime
    channel_id: int
    channel_name: str | None
    author_username: str | None
    author_global_name: str | None
    author_avatar_url: str | None


@dataclass(frozen=True)
class AuthorRow:
    """A user who has posted in scope, with how much and when."""

    user: User
    messages: int
    first_seen: datetime
    last_seen: datetime


class AuthorSort(StrEnum):
    """How ``authors()`` orders its rows. Ties are broken by user id."""

    MESSAGES = "messages"
    NAME = "name"
    RECENT = "recent"


@dataclass(frozen=True)
class Summary:
    """Aggregates over the messages in a scope."""

    messages: int = 0
    attachments: int = 0
    reactions: int = 0
    authors: int = 0
    channels: int = 0
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    average_length: float = 0.0


@dataclass(frozen=True)
class ChannelActivity:
    """How many messages in scope a channel holds, counted live."""

    channel_id: int
    channel_name: str
    messages: int


@dataclass(frozen=True)
class TopChannel:
    """A channel with the message count the ingest keeps for it."""

    channel_id: int
    name: str
    message_count: int


@dataclass(frozen=True)
class ReactionTotal:
    """How often one emoji was reacted to messages in scope."""

    emoji_name: str | None
    count: int


class Period(StrEnum):
    """The calendar bucket of an activity read."""

    MONTH = "month"
    WEEK = "week"


@dataclass(frozen=True)
class ActivityBucket:
    """Messages in one calendar month or ISO week, starting on ``start``."""

    start: date
    messages: int


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
    rows: Select[*tuple[Any, ...]],
    where: Sequence[ColumnElement[bool]],
    count_from: Any | None,
    *,
    limit: int,
    offset: int = 0,
    paging: Sequence[ColumnElement[bool]] = (),
) -> tuple[list[Any], int, bool]:
    """Fetch one page of ``rows`` and the total of everything ``where`` matches.

    Over-fetches one row past ``limit`` for ``has_more``. The ``count(*)`` over
    ``count_from`` uses the same ``where`` as the rows (``paging`` narrows the rows
    only) and is skipped when the first page is already the whole result. A
    ``count_from`` of ``None`` counts the rows statement itself, for grouped reads.

    Returns:
        The rows of the page, the total and whether more rows follow
    """
    result = await session.execute(rows.where(*where, *paging).offset(offset).limit(limit + 1))
    fetched = list(result.all())
    has_more = len(fetched) > limit
    fetched = fetched[:limit]
    if offset == 0 and not paging and not has_more:
        return fetched, len(fetched), False
    if count_from is None:
        counting = select(func.count()).select_from(rows.where(*where).order_by(None).subquery())
    else:
        counting = select(func.count()).select_from(count_from).where(*where)
    counted = await session.execute(counting)
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


async def guilds(session: AsyncSession) -> list[Guild]:
    """Every archived guild, by id."""
    result = await session.execute(select(Guild).order_by(Guild.id))
    return list(result.scalars().all())


async def guild(session: AsyncSession, guild_id: int) -> Guild | None:
    """One archived guild, or ``None`` if the archive does not hold it."""
    result = await session.execute(select(Guild).where(Guild.id == guild_id))
    return result.scalar_one_or_none()


async def guild_channels(session: AsyncSession, guild_id: int) -> list[Channel]:
    """A guild's channels in position order, ties broken by id."""
    result = await session.execute(
        select(Channel).where(Channel.guild_id == guild_id).order_by(Channel.position, Channel.id)
    )
    return list(result.scalars().all())


async def guild_counts(session: AsyncSession, guild_ids: Sequence[int]) -> dict[int, GuildCounts]:
    """Live channel and message counts for each of ``guild_ids``, in two statements.

    Every requested id is in the result; a guild with nothing archived counts zero.
    """
    channel_counts = await session.execute(
        select(Channel.guild_id, func.count())
        .where(Channel.guild_id.in_(guild_ids))
        .group_by(Channel.guild_id)
    )
    message_counts = await session.execute(
        select(Channel.guild_id, func.count())
        .select_from(Message)
        .join(Channel, Message.channel_id == Channel.id)
        .where(Channel.guild_id.in_(guild_ids))
        .group_by(Channel.guild_id)
    )
    channels: dict[int, int] = dict(channel_counts.all())
    messages: dict[int, int] = dict(message_counts.all())
    return {
        gid: GuildCounts(channels=channels.get(gid, 0), messages=messages.get(gid, 0))
        for gid in guild_ids
    }


async def attachments(
    session: AsyncSession,
    scope: Scope,
    *,
    kind: MediaKind,
    limit: int,
    offset: int = 0,
) -> Page[AttachmentRow]:
    """Attachments of a media kind on messages in scope, newest message first.

    Ties on the message time are broken by attachment id, newest first. The channel
    name and author come from joins.
    """
    where = [*_message_scope(scope), Attachment.content_type.in_(kind.content_types)]
    rows = (
        select(
            Attachment,
            Message.created_at,
            Message.channel_id,
            Channel.name,
            User.username,
            User.global_name,
            User.avatar_url,
        )
        .join(Message, Attachment.message_id == Message.id)
        .outerjoin(Channel, Message.channel_id == Channel.id)
        .outerjoin(User, Message.author_id == User.id)
        .order_by(Message.created_at.desc(), Attachment.id.desc())
    )
    fetched, total, has_more = await _page(
        session,
        rows,
        where,
        join(Attachment, Message, Attachment.message_id == Message.id),
        limit=limit,
        offset=offset,
    )
    return Page(
        rows=[AttachmentRow(*row) for row in fetched],
        total=total,
        has_more=has_more,
    )


async def user(session: AsyncSession, user_id: int) -> User | None:
    """One user, or ``None`` if the archive does not hold them."""
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def authors(
    session: AsyncSession,
    scope: Scope,
    *,
    sort: AuthorSort,
    limit: int,
    offset: int = 0,
    name: str | None = None,
) -> Page[AuthorRow]:
    """The users with at least one message in scope, with counts and first and last seen.

    ``name`` matches the username or global name case-insensitively, with LIKE
    wildcards taken literally.
    """
    where = _message_scope(scope)
    if name is not None:
        pattern = f"%{escape_like(name)}%"
        where.append(
            or_(
                User.username.ilike(pattern, escape="\\"),
                User.global_name.ilike(pattern, escape="\\"),
            )
        )
    messages = func.count()
    last_seen = func.max(Message.created_at)
    ordering: dict[AuthorSort, ColumnElement[Any]] = {
        AuthorSort.MESSAGES: messages.desc(),
        AuthorSort.NAME: User.username.asc(),
        AuthorSort.RECENT: last_seen.desc(),
    }
    rows = (
        select(User, messages, func.min(Message.created_at), last_seen)
        .join(Message, Message.author_id == User.id)
        .group_by(User.id)
        .order_by(ordering[AuthorSort(sort)], User.id.asc())
    )
    fetched, total, has_more = await _page(session, rows, where, None, limit=limit, offset=offset)
    return Page(rows=[AuthorRow(*row) for row in fetched], total=total, has_more=has_more)


async def summary(session: AsyncSession, scope: Scope) -> Summary:
    """Message, attachment, reaction, author and channel totals over a scope."""
    where = _message_scope(scope)
    in_scope = select(Message.id).where(*where)
    messages = await session.execute(
        select(
            func.count(),
            func.count(func.distinct(Message.author_id)),
            func.count(func.distinct(Message.channel_id)),
            func.min(Message.created_at),
            func.max(Message.created_at),
            func.avg(func.length(Message.content)),
        ).where(*where)
    )
    total, authors_, channels, first, last, average = messages.one()
    attachments = await session.execute(
        select(func.count()).select_from(Attachment).where(Attachment.message_id.in_(in_scope))
    )
    reactions_ = await session.execute(
        select(func.coalesce(func.sum(Reaction.count), 0)).where(Reaction.message_id.in_(in_scope))
    )
    return Summary(
        messages=int(total),
        attachments=int(attachments.scalar_one()),
        reactions=int(reactions_.scalar_one()),
        authors=int(authors_),
        channels=int(channels),
        first_message_at=first,
        last_message_at=last,
        average_length=float(average or 0),
    )


async def channel_activity(
    session: AsyncSession, scope: Scope, *, limit: int
) -> list[ChannelActivity]:
    """The channels holding the most messages in scope, counted live, ties by id."""
    messages = func.count()
    result = await session.execute(
        select(Channel.id, Channel.name, messages)
        .join(Message, Message.channel_id == Channel.id)
        .where(*_message_scope(scope))
        .group_by(Channel.id, Channel.name)
        .order_by(messages.desc(), Channel.id.asc())
        .limit(limit)
    )
    return [ChannelActivity(*row) for row in result.all()]


async def reactions(session: AsyncSession, scope: Scope, *, limit: int) -> list[ReactionTotal]:
    """The emoji most reacted to messages in scope, ties by emoji name."""
    total = func.sum(Reaction.count)
    result = await session.execute(
        select(Reaction.emoji_name, total)
        .join(Message, Reaction.message_id == Message.id)
        .where(*_message_scope(scope))
        .group_by(Reaction.emoji_name)
        .order_by(total.desc(), Reaction.emoji_name.asc())
        .limit(limit)
    )
    return [ReactionTotal(name, int(count)) for name, count in result.all()]


async def activity(
    session: AsyncSession,
    scope: Scope,
    *,
    period: Period,
    since: datetime | None = None,
) -> list[ActivityBucket]:
    """Messages per calendar month or ISO week over a scope, oldest first.

    Only buckets holding messages are returned. SQL groups by day with ``extract``
    and the days are folded into periods here, so no dialect-bound date function
    is emitted. ``since`` is inclusive; an aware datetime is converted to naive UTC.
    """
    where = _message_scope(scope)
    if since is not None:
        where.append(Message.created_at >= _naive_utc(since))
    year = extract("year", Message.created_at)
    month = extract("month", Message.created_at)
    day = extract("day", Message.created_at)
    result = await session.execute(
        select(year, month, day, func.count()).where(*where).group_by(year, month, day)
    )
    buckets: dict[date, int] = {}
    for y, m, d, count in result.all():
        on = date(int(y), int(m), int(d))
        start = on - timedelta(days=on.weekday()) if period is Period.WEEK else on.replace(day=1)
        buckets[start] = buckets.get(start, 0) + int(count)
    return [ActivityBucket(start, buckets[start]) for start in sorted(buckets)]


async def top_channels(session: AsyncSession, guild_id: int, *, limit: int) -> list[TopChannel]:
    """A guild's busiest channels, ties by id.

    Ranked by ``Channel.message_count``, the counter the ingest maintains, not by a
    live count of messages: whether that counter survives is a separate decision.
    """
    result = await session.execute(
        select(Channel.id, Channel.name, Channel.message_count)
        .where(Channel.guild_id == guild_id)
        .order_by(Channel.message_count.desc(), Channel.id.asc())
        .limit(limit)
    )
    return [TopChannel(*row) for row in result.all()]
