"""Direct tests for archive reads (``wumpus_archiver.storage.archive_reads``)."""

import ast
import itertools
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import (
    ActivityBucket,
    AttachmentRow,
    AuthorRow,
    AuthorSort,
    ChannelActivity,
    GuildCounts,
    Has,
    MediaKind,
    Order,
    Page,
    Period,
    ReactionTotal,
    Scope,
    Summary,
    TopChannel,
    escape_like,
)
from wumpus_archiver.storage.database import Database


class TestMediaKind:
    """The one home of the media content-type lists."""

    def test_image_types(self) -> None:
        assert MediaKind.IMAGE.content_types == (
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "image/avif",
        )

    def test_gif_types(self) -> None:
        assert MediaKind.GIF.content_types == ("image/gif",)

    def test_video_types(self) -> None:
        assert MediaKind.VIDEO.content_types == ("video/mp4", "video/webm", "video/quicktime")

    def test_gif_is_a_distinct_kind_although_images_include_gifs(self) -> None:
        assert MediaKind.GIF is not MediaKind.IMAGE
        assert set(MediaKind.GIF.content_types) < set(MediaKind.IMAGE.content_types)


def test_escape_like_is_still_importable_from_the_route_helpers() -> None:
    from wumpus_archiver.api.routes._helpers import escape_like as reexported

    assert reexported is escape_like


class TestEscapeLike:
    """Unit tests for escape_like."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("", ""),
            ("plain text", "plain text"),
            ("%", "\\%"),
            ("_", "\\_"),
            ("\\", "\\\\"),
            ("100%_real", "100\\%\\_real"),
            ("%_%", "\\%\\_\\%"),
            # The escape character must be escaped first, so it is not double-processed.
            ("a\\%", "a\\\\\\%"),
            ("a\\_b", "a\\\\\\_b"),
        ],
    )
    def test_default_escape(self, value: str, expected: str) -> None:
        """Test that %, _ and the backslash are each prefixed with a backslash."""
        assert escape_like(value) == expected

    def test_custom_escape_character(self) -> None:
        """Test escaping with a non-default escape character."""
        assert escape_like("a!b%c_d", escape="!") == "a!!b!%c!_d"

    def test_backslash_is_not_special_with_custom_escape(self) -> None:
        """Test that a backslash is left alone when another escape character is used."""
        assert escape_like("a\\b", escape="!") == "a\\b"


# --- messages() over one seeded archive -------------------------------------------------

GUILD = 1
OTHER_GUILD = 2
EMPTY_GUILD = 3
CHANNEL = 10
SIBLING_CHANNEL = 11
FOREIGN_CHANNEL = 20
QUIET_CHANNEL = 12  # first by position, no messages
ALICE = 100
BOB = 101
CAROL = 102  # shares Alice's username; her global name holds a LIKE wildcard
T0 = datetime(2024, 1, 31, 22, 0, 0)

# (id, channel, author, minutes after T0, content). Ids 5 and 6 share a timestamp: the tie.
# Ids are deliberately not in time order (9 is older than 8) so ids and time disagree.
SEED_MESSAGES: list[tuple[int, int, int, int, str]] = [
    (1, CHANNEL, ALICE, 0, "first"),
    (2, CHANNEL, BOB, 10, "see https://example.test"),
    (3, CHANNEL, ALICE, 20, "with an image"),
    (4, CHANNEL, BOB, 30, "with a video"),
    (5, CHANNEL, ALICE, 40, "tie a"),
    (6, CHANNEL, BOB, 40, "tie b"),
    (7, CHANNEL, ALICE, 50, "with a file"),
    (9, CHANNEL, BOB, 60, "older than eight"),
    (8, CHANNEL, ALICE, 70, "last"),
    (30, SIBLING_CHANNEL, ALICE, 5, "sibling"),
    (31, SIBLING_CHANNEL, BOB, 15, "100% Sure"),
    (32, SIBLING_CHANNEL, ALICE, 25, "snake_case TIE"),
    (33, SIBLING_CHANNEL, BOB, 145, "back\\slash at https://x.test"),
    (40, FOREIGN_CHANNEL, BOB, 5, "foreign"),
    (41, FOREIGN_CHANNEL, ALICE, 15, "100% elsewhere"),
    (42, FOREIGN_CHANNEL, CAROL, 15, "carol abroad"),
    (43, SIBLING_CHANNEL, CAROL, -31 * 24 * 60, "new year's eve"),  # 2023-12-31 22:00
]
# Channel 10 in time order, (created_at, id) ascending.
CHANNEL_ORDER = [1, 2, 3, 4, 5, 6, 7, 9, 8]

# (id, message, content_type)
SEED_ATTACHMENTS: list[tuple[int, int, str | None]] = [
    (501, 3, "image/png"),
    (502, 4, "video/mp4"),
    (503, 7, "application/pdf"),
    (504, 32, "image/gif"),
    (505, 41, "image/png"),
    (506, 3, "image/webp"),  # a second image on message 3: the id tie-break
]

# (message, emoji, count): Bob's messages; "party" and "thumbs" tie on 3.
SEED_REACTIONS: list[tuple[int, str | None, int]] = [
    (2, "thumbs", 3),
    (2, "party", 1),
    (4, "party", 2),
    (4, None, 1),
]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def archive(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[Database]:
    """One seeded archive shared by every test in this file."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('reads') / 'archive.db'}")
    await db.connect()
    await db.create_tables()
    async with db.session() as session:
        session.add_all(
            [
                Guild(id=GUILD, name="one"),
                Guild(id=OTHER_GUILD, name="two"),
                Guild(id=EMPTY_GUILD, name="empty"),
            ]
        )
        session.add_all(
            [
                # The message_count counters are the ingest's, deliberately not live counts.
                Channel(id=CHANNEL, guild_id=GUILD, name="general", type=0, message_count=9),
                Channel(id=SIBLING_CHANNEL, guild_id=GUILD, name="random", type=0, message_count=4),
                Channel(
                    id=FOREIGN_CHANNEL,
                    guild_id=OTHER_GUILD,
                    name="elsewhere",
                    type=0,
                    message_count=2,
                ),
                Channel(
                    id=QUIET_CHANNEL,
                    guild_id=GUILD,
                    name="news",
                    type=0,
                    position=-1,
                    message_count=4,
                ),
            ]
        )
        session.add_all(
            [
                User(id=ALICE, username="alice"),
                User(id=BOB, username="bob"),
                User(id=CAROL, username="alice", global_name="100% Carol"),
            ]
        )
        for message_id, channel_id, author_id, minutes, content in SEED_MESSAGES:
            session.add(
                Message(
                    id=message_id,
                    channel_id=channel_id,
                    author_id=author_id,
                    content=content,
                    clean_content=content,
                    created_at=T0 + timedelta(minutes=minutes),
                    scraped_at=T0,
                )
            )
        for attachment_id, message_id, content_type in SEED_ATTACHMENTS:
            session.add(
                Attachment(
                    id=attachment_id,
                    message_id=message_id,
                    filename=f"{attachment_id}.bin",
                    content_type=content_type,
                    size=1,
                    url=f"https://cdn.example.test/{attachment_id}",
                )
            )
        for message_id, emoji_name, count in SEED_REACTIONS:
            session.add(Reaction(message_id=message_id, emoji_name=emoji_name, count=count))
    yield db
    await db.disconnect()


@pytest_asyncio.fixture(loop_scope="module")
async def reads(archive: Database) -> AsyncIterator[AsyncSession]:
    async with archive.session() as session:
        yield session


@pytest.fixture
def statements(archive: Database) -> Iterator[list[str]]:
    """The SQL statements executed while the test runs."""
    seen: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        seen.append(statement)

    engine = archive.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    yield seen
    event.remove(engine, "before_cursor_execute", record)


def _ids(page: Page[Message]) -> list[int]:
    return [message.id for message in page.rows]


def _counts(statements: list[str]) -> int:
    return sum("count(*)" in statement for statement in statements)


IN_CHANNEL = Scope(channel=CHANNEL)
OLDEST = Order.OLDEST_FIRST
NEWEST = Order.NEWEST_FIRST

in_module_loop = pytest.mark.asyncio(loop_scope="module")


@in_module_loop
class TestMessagesOrder:
    async def test_oldest_first_with_a_primary_key_tie_break(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=50)
        assert _ids(page) == CHANNEL_ORDER

    async def test_newest_first_is_the_exact_reverse(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=NEWEST, limit=50)
        assert _ids(page) == CHANNEL_ORDER[::-1]

    @pytest.mark.parametrize("order", [OLDEST, NEWEST])
    async def test_oldest_and_newest_ids_do_not_depend_on_order(
        self, reads: AsyncSession, order: Order
    ) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=order, limit=50)
        assert (page.oldest_id, page.newest_id) == (1, 8)

    async def test_related_rows_are_loaded(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=3)
        third = page.rows[2]
        assert third.author is not None and third.author.username == "alice"
        assert {a.id for a in third.attachments} == {501, 506}
        assert third.reactions == []


@in_module_loop
class TestMessagesCursors:
    @pytest.mark.parametrize(("order", "expected"), [(OLDEST, [3, 4, 5]), (NEWEST, [5, 4, 3])])
    async def test_before_returns_the_adjacent_older_page(
        self, reads: AsyncSession, order: Order, expected: list[int]
    ) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=order, limit=3, before=6)
        assert _ids(page) == expected
        assert page.has_more is True

    @pytest.mark.parametrize(("order", "expected"), [(OLDEST, [6, 7, 9]), (NEWEST, [9, 7, 6])])
    async def test_after_returns_the_adjacent_newer_page(
        self, reads: AsyncSession, order: Order, expected: list[int]
    ) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=order, limit=3, after=5)
        assert _ids(page) == expected
        assert page.has_more is True

    async def test_after_the_last_full_page_has_no_more(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=3, after=7)
        assert _ids(page) == [9, 8]
        assert page.has_more is False

    async def test_before_and_after_bound_the_page_on_both_sides(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(
            reads, IN_CHANNEL, order=OLDEST, limit=10, before=7, after=3
        )
        assert _ids(page) == [4, 5, 6]

    @pytest.mark.parametrize("cursor", ["before", "after"])
    @pytest.mark.parametrize("order", [OLDEST, NEWEST])
    async def test_an_unknown_cursor_falls_back_to_the_first_page(
        self, reads: AsyncSession, cursor: str, order: Order
    ) -> None:
        first = await archive_reads.messages(reads, IN_CHANNEL, order=order, limit=3)
        page = await archive_reads.messages(
            reads, IN_CHANNEL, order=order, limit=3, **{cursor: 999_999}
        )
        assert _ids(page) == _ids(first)

    async def test_paging_back_from_the_newest_walks_the_whole_channel(
        self, reads: AsyncSession
    ) -> None:
        seen: list[int] = []
        page = await archive_reads.messages(reads, IN_CHANNEL, order=NEWEST, limit=2)
        seen += _ids(page)
        while page.has_more:
            page = await archive_reads.messages(
                reads, IN_CHANNEL, order=NEWEST, limit=2, before=page.oldest_id
            )
            seen += _ids(page)
        assert seen == CHANNEL_ORDER[::-1]


@in_module_loop
class TestMessagesTotals:
    @pytest.mark.parametrize("kwargs", [{}, {"before": 6}, {"after": 5}, {"before": 8, "after": 1}])
    async def test_total_ignores_paging(self, reads: AsyncSession, kwargs: dict[str, int]) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=2, **kwargs)
        assert page.total == len(CHANNEL_ORDER)

    async def test_has_more_comes_from_the_over_fetch(self, reads: AsyncSession) -> None:
        exact = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=9)
        short = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=8)
        assert (exact.has_more, short.has_more) == (False, True)

    async def test_count_is_skipped_when_the_first_page_is_everything(
        self, reads: AsyncSession, statements: list[str]
    ) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=50)
        assert page.total == len(CHANNEL_ORDER)
        assert _counts(statements) == 0

    async def test_count_runs_once_when_more_rows_follow(
        self, reads: AsyncSession, statements: list[str]
    ) -> None:
        await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=2)
        assert _counts(statements) == 1

    async def test_count_runs_once_on_a_cursor_page(
        self, reads: AsyncSession, statements: list[str]
    ) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=50, after=7)
        assert page.total == len(CHANNEL_ORDER)
        assert _counts(statements) == 1

    async def test_empty_scope_is_the_whole_archive(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(reads, Scope(), order=OLDEST, limit=50)
        assert page.total == len(SEED_MESSAGES)


@in_module_loop
class TestMessagesScopeAndFilters:
    async def test_guild_scope_covers_its_channels_only(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(reads, Scope(guild=GUILD), order=OLDEST, limit=50)
        assert set(_ids(page)) == {m[0] for m in SEED_MESSAGES if m[1] != FOREIGN_CHANNEL}

    async def test_a_channel_outside_the_guild_yields_an_empty_page(
        self, reads: AsyncSession
    ) -> None:
        page = await archive_reads.messages(
            reads, Scope(guild=GUILD, channel=FOREIGN_CHANNEL), order=OLDEST, limit=50
        )
        assert (page.rows, page.total, page.has_more) == ([], 0, False)
        assert (page.oldest_id, page.newest_id) == (None, None)

    async def test_author_scope(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(
            reads, Scope(channel=CHANNEL, author=BOB), order=OLDEST, limit=50
        )
        assert _ids(page) == [2, 4, 6, 9]

    @pytest.mark.parametrize(
        ("has", "expected"),
        [(Has.FILE, [3, 4, 7]), (Has.IMAGE, [3]), (Has.VIDEO, [4]), (Has.LINK, [2])],
    )
    async def test_has(self, reads: AsyncSession, has: Has, expected: list[int]) -> None:
        page = await archive_reads.messages(reads, IN_CHANNEL, order=OLDEST, limit=50, has=has)
        assert _ids(page) == expected
        assert page.total == len(expected)

    async def test_since_is_inclusive_and_until_exclusive(self, reads: AsyncSession) -> None:
        page = await archive_reads.messages(
            reads,
            IN_CHANNEL,
            order=OLDEST,
            limit=50,
            since=T0 + timedelta(minutes=20),
            until=T0 + timedelta(minutes=40),
        )
        assert _ids(page) == [3, 4]

    async def test_an_aware_since_behaves_like_its_naive_utc_equivalent(
        self, reads: AsyncSession
    ) -> None:
        naive = T0 + timedelta(minutes=40)
        aware = naive.replace(tzinfo=UTC).astimezone(timezone(timedelta(hours=-5)))
        by_naive = await archive_reads.messages(
            reads, IN_CHANNEL, order=OLDEST, limit=50, since=naive
        )
        by_aware = await archive_reads.messages(
            reads, IN_CHANNEL, order=OLDEST, limit=50, since=aware
        )
        assert _ids(by_aware) == _ids(by_naive) == [5, 6, 7, 9, 8]


@in_module_loop
async def test_reads_leave_the_session_clean(reads: AsyncSession) -> None:
    await archive_reads.messages(reads, Scope(), order=OLDEST, limit=2, has=Has.FILE)
    assert not reads.new and not reads.dirty and not reads.deleted


def test_the_module_only_reads_and_imports_models_only() -> None:
    source = Path(archive_reads.__file__).read_text()
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(name.startswith(("fastapi", "wumpus_archiver.api")) for name in imported)
    internal = {name for name in imported if name.startswith("wumpus_archiver.")}
    assert all(name.startswith("wumpus_archiver.models.") for name in internal), internal
    for call in ("commit", "flush", "close", "add", "delete", "merge", "rollback"):
        assert f"session.{call}(" not in source


# --- search: total agrees with the rows for every filter combination ---------------------

GUILD_OF = {
    CHANNEL: GUILD,
    SIBLING_CHANNEL: GUILD,
    QUIET_CHANNEL: GUILD,
    FOREIGN_CHANNEL: OTHER_GUILD,
}
SINCE = T0 + timedelta(minutes=15)
UNTIL = T0 + timedelta(minutes=60)
WINDOWS: dict[str, tuple[datetime | None, datetime | None]] = {
    "any time": (None, None),
    "naive window": (SINCE, UNTIL),
    "aware window": (
        SINCE.replace(tzinfo=UTC).astimezone(timezone(timedelta(hours=-5))),
        UNTIL.replace(tzinfo=UTC).astimezone(timezone(timedelta(hours=3))),
    ),
}
SCOPES: dict[str, Scope] = {
    "archive": Scope(),
    "guild": Scope(guild=GUILD),
    "channel in guild": Scope(guild=GUILD, channel=SIBLING_CHANNEL),
    "channel outside guild": Scope(guild=GUILD, channel=FOREIGN_CHANNEL),
    "author": Scope(author=BOB),
    "guild and author": Scope(guild=GUILD, author=ALICE),
}
# Backslash and longer patterns are covered over HTTP in test_api_search.py.
TEXTS = [None, "%", "_", "TIE"]


def _carries(message_id: int, content: str, has: Has) -> bool:
    if has is Has.LINK:
        return "http://" in content or "https://" in content
    types = [ct for _, carrier, ct in SEED_ATTACHMENTS if carrier == message_id]
    if has is Has.IMAGE:
        return any(ct in MediaKind.IMAGE.content_types for ct in types)
    if has is Has.VIDEO:
        return any(ct in MediaKind.VIDEO.content_types for ct in types)
    return bool(types)


def _expected(
    scope: Scope, text: str | None, has: Has | None, window: tuple[datetime | None, datetime | None]
) -> set[int]:
    since, until = (
        None if bound is None else bound.astimezone(UTC).replace(tzinfo=None) for bound in window
    )
    return {
        message_id
        for message_id, channel_id, author_id, minutes, content in SEED_MESSAGES
        if (scope.guild is None or GUILD_OF[channel_id] == scope.guild)
        and (scope.channel is None or channel_id == scope.channel)
        and (scope.author is None or author_id == scope.author)
        and (text is None or text.lower() in content.lower())
        and (has is None or _carries(message_id, content, has))
        and (since is None or T0 + timedelta(minutes=minutes) >= since)
        and (until is None or T0 + timedelta(minutes=minutes) < until)
    }


@in_module_loop
@pytest.mark.parametrize("window", list(WINDOWS))
@pytest.mark.parametrize("scope", list(SCOPES))
async def test_total_agrees_with_the_rows(reads: AsyncSession, scope: str, window: str) -> None:
    """Every text and ``has`` under this scope and window; the case names the failing pair."""
    since, until = WINDOWS[window]
    for text, has in itertools.product(TEXTS, [None, *Has]):
        case = f"text={text!r} has={has}"
        kwargs: dict[str, Any] = {"text": text, "has": has, "since": since, "until": until}
        page = await archive_reads.messages(reads, SCOPES[scope], order=NEWEST, limit=100, **kwargs)
        expected = _expected(SCOPES[scope], text, has, WINDOWS[window])
        assert page.total == len(page.rows), case
        assert set(_ids(page)) == expected, case


def test_no_route_looks_up_channel_names_for_search_results() -> None:
    from wumpus_archiver.api.routes import search

    source = Path(search.__file__).read_text()
    assert "Channel" not in source
    assert "select(" not in source


# --- guilds and channels -------------------------------------------------------------------


@in_module_loop
class TestGuildReads:
    async def test_guilds_by_id(self, reads: AsyncSession) -> None:
        assert [g.id for g in await archive_reads.guilds(reads)] == [
            GUILD,
            OTHER_GUILD,
            EMPTY_GUILD,
        ]

    async def test_guild_or_none(self, reads: AsyncSession) -> None:
        found = await archive_reads.guild(reads, OTHER_GUILD)
        assert found is not None and found.name == "two"
        assert await archive_reads.guild(reads, 999) is None

    async def test_channels_in_position_order_with_an_id_tie_break(
        self, reads: AsyncSession
    ) -> None:
        channels = await archive_reads.guild_channels(reads, GUILD)
        assert [c.id for c in channels] == [QUIET_CHANNEL, CHANNEL, SIBLING_CHANNEL]
        assert await archive_reads.guild_channels(reads, EMPTY_GUILD) == []

    async def test_counts_equal_live_counts(self, reads: AsyncSession) -> None:
        counts = await archive_reads.guild_counts(reads, [GUILD, OTHER_GUILD, EMPTY_GUILD, 999])
        in_guild = sum(1 for m in SEED_MESSAGES if GUILD_OF[m[1]] == GUILD)
        in_other = sum(1 for m in SEED_MESSAGES if GUILD_OF[m[1]] == OTHER_GUILD)
        assert counts == {
            GUILD: GuildCounts(channels=3, messages=in_guild),
            OTHER_GUILD: GuildCounts(channels=1, messages=in_other),
            EMPTY_GUILD: GuildCounts(),
            999: GuildCounts(),
        }

    @pytest.mark.parametrize("guild_ids", [[], [GUILD], [GUILD, OTHER_GUILD, EMPTY_GUILD]])
    async def test_counts_take_two_statements_however_many_guilds(
        self, reads: AsyncSession, statements: list[str], guild_ids: list[int]
    ) -> None:
        await archive_reads.guild_counts(reads, guild_ids)
        assert len(statements) == 2


# --- attachments ---------------------------------------------------------------------------


def _attachment_ids(page: Page[AttachmentRow]) -> list[int]:
    return [row.attachment.id for row in page.rows]


@in_module_loop
class TestAttachments:
    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            (MediaKind.IMAGE, [504, 506, 501]),
            (MediaKind.GIF, [504]),
            (MediaKind.VIDEO, [502]),
        ],
    )
    async def test_media_kind_newest_first_with_an_id_tie_break(
        self, reads: AsyncSession, kind: MediaKind, expected: list[int]
    ) -> None:
        page = await archive_reads.attachments(reads, Scope(guild=GUILD), kind=kind, limit=50)
        assert _attachment_ids(page) == expected
        assert (page.total, page.has_more) == (len(expected), False)

    async def test_offset_paging(self, reads: AsyncSession) -> None:
        scope = Scope(guild=GUILD)
        pages = [
            await archive_reads.attachments(
                reads, scope, kind=MediaKind.IMAGE, limit=2, offset=offset
            )
            for offset in (0, 2, 4)
        ]
        assert [_attachment_ids(p) for p in pages] == [[504, 506], [501], []]
        assert [p.has_more for p in pages] == [True, False, False]
        assert [p.total for p in pages] == [3, 3, 3]

    async def test_author_filter(self, reads: AsyncSession) -> None:
        alice = await archive_reads.attachments(
            reads, Scope(author=ALICE), kind=MediaKind.IMAGE, limit=50
        )
        bob = await archive_reads.attachments(
            reads, Scope(author=BOB), kind=MediaKind.IMAGE, limit=50
        )
        assert _attachment_ids(alice) == [504, 506, 501, 505]
        assert (bob.rows, bob.total) == ([], 0)

    async def test_a_channel_outside_the_guild_yields_an_empty_page(
        self, reads: AsyncSession
    ) -> None:
        page = await archive_reads.attachments(
            reads, Scope(guild=GUILD, channel=FOREIGN_CHANNEL), kind=MediaKind.IMAGE, limit=50
        )
        assert (page.rows, page.total, page.has_more) == ([], 0, False)

    async def test_rows_carry_channel_and_author(self, reads: AsyncSession) -> None:
        page = await archive_reads.attachments(
            reads, Scope(channel=SIBLING_CHANNEL), kind=MediaKind.GIF, limit=50
        )
        (row,) = page.rows
        assert (row.channel_id, row.channel_name, row.author_username) == (
            SIBLING_CHANNEL,
            "random",
            "alice",
        )
        assert row.created_at == T0 + timedelta(minutes=25)

    @pytest.mark.parametrize(("limit", "counts"), [(50, 0), (1, 1)])
    async def test_one_page_is_one_statement_plus_at_most_one_count(
        self, reads: AsyncSession, statements: list[str], limit: int, counts: int
    ) -> None:
        await archive_reads.attachments(
            reads, Scope(guild=GUILD), kind=MediaKind.IMAGE, limit=limit
        )
        assert len(statements) == 1 + counts
        assert _counts(statements) == counts


# --- authors, profile aggregates and activity ----------------------------------------------


def _user_ids(page: Page[AuthorRow]) -> list[int]:
    return [row.user.id for row in page.rows]


@in_module_loop
class TestAuthors:
    @pytest.mark.parametrize(
        ("sort", "scope", "expected"),
        [
            (AuthorSort.MESSAGES, Scope(), [ALICE, BOB, CAROL]),
            (AuthorSort.MESSAGES, Scope(channel=SIBLING_CHANNEL), [ALICE, BOB, CAROL]),
            (AuthorSort.NAME, Scope(), [ALICE, CAROL, BOB]),
            (AuthorSort.RECENT, Scope(), [BOB, ALICE, CAROL]),
            (AuthorSort.RECENT, Scope(channel=FOREIGN_CHANNEL), [ALICE, CAROL, BOB]),
        ],
        ids=[
            "messages",
            "messages tie",
            "name tie",
            "recent",
            "recent tie",
        ],
    )
    async def test_sort_with_a_user_id_tie_break(
        self, reads: AsyncSession, sort: AuthorSort, scope: Scope, expected: list[int]
    ) -> None:
        page = await archive_reads.authors(reads, scope, sort=sort, limit=50)
        assert _user_ids(page) == expected

    async def test_counts_and_first_and_last_seen(self, reads: AsyncSession) -> None:
        page = await archive_reads.authors(
            reads, Scope(guild=GUILD), sort=AuthorSort.MESSAGES, limit=50
        )
        alice = page.rows[0]
        assert (alice.user.id, alice.messages) == (ALICE, 7)
        assert (alice.first_seen, alice.last_seen) == (T0, T0 + timedelta(minutes=70))

    @pytest.mark.parametrize(
        ("scope", "expected"),
        [
            (Scope(guild=GUILD), {ALICE: 7, BOB: 6, CAROL: 1}),
            (Scope(guild=OTHER_GUILD), {ALICE: 1, BOB: 1, CAROL: 1}),
            (Scope(guild=EMPTY_GUILD), {}),
            (Scope(guild=GUILD, author=BOB), {BOB: 6}),
        ],
    )
    async def test_scope(self, reads: AsyncSession, scope: Scope, expected: dict[int, int]) -> None:
        page = await archive_reads.authors(reads, scope, sort=AuthorSort.MESSAGES, limit=50)
        assert {row.user.id: row.messages for row in page.rows} == expected
        assert page.total == len(expected)

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("ALI", {ALICE, CAROL}), ("%", {CAROL}), ("_", set()), ("100% c", {CAROL})],
    )
    async def test_name_search_takes_wildcards_literally(
        self, reads: AsyncSession, name: str, expected: set[int]
    ) -> None:
        page = await archive_reads.authors(
            reads, Scope(), sort=AuthorSort.NAME, limit=50, name=name
        )
        assert set(_user_ids(page)) == expected
        assert page.total == len(expected)

    async def test_paging(self, reads: AsyncSession) -> None:
        first = await archive_reads.authors(reads, Scope(), sort=AuthorSort.NAME, limit=2)
        rest = await archive_reads.authors(reads, Scope(), sort=AuthorSort.NAME, limit=2, offset=2)
        assert (_user_ids(first), first.total, first.has_more) == ([ALICE, CAROL], 3, True)
        assert (_user_ids(rest), rest.total, rest.has_more) == ([BOB], 3, False)

    async def test_an_unknown_sort_is_refused(self, reads: AsyncSession) -> None:
        with pytest.raises(ValueError):
            await archive_reads.authors(reads, Scope(), sort="loudest", limit=5)  # type: ignore[arg-type]


@in_module_loop
class TestProfileReads:
    async def test_summary(self, reads: AsyncSession) -> None:
        scope = Scope(guild=GUILD, author=ALICE)
        contents = [m[4] for m in SEED_MESSAGES if m[2] == ALICE and GUILD_OF[m[1]] == GUILD]
        assert await archive_reads.summary(reads, scope) == Summary(
            messages=7,
            attachments=4,
            reactions=0,
            authors=1,
            channels=2,
            first_message_at=T0,
            last_message_at=T0 + timedelta(minutes=70),
            average_length=pytest.approx(sum(map(len, contents)) / len(contents)),
        )

    async def test_summary_of_an_empty_scope(self, reads: AsyncSession) -> None:
        assert await archive_reads.summary(reads, Scope(guild=EMPTY_GUILD)) == Summary()

    async def test_summary_sums_reaction_counts(self, reads: AsyncSession) -> None:
        summary = await archive_reads.summary(reads, Scope(author=BOB))
        assert summary.reactions == sum(count for _, _, count in SEED_REACTIONS)

    async def test_reactions_ranked_with_a_name_tie_break(self, reads: AsyncSession) -> None:
        assert await archive_reads.reactions(reads, Scope(author=BOB), limit=10) == [
            ReactionTotal("party", 3),
            ReactionTotal("thumbs", 3),
            ReactionTotal(None, 1),
        ]
        assert await archive_reads.reactions(reads, Scope(author=ALICE), limit=10) == []

    async def test_channel_activity_ranked_with_an_id_tie_break(self, reads: AsyncSession) -> None:
        assert await archive_reads.channel_activity(reads, Scope(author=CAROL), limit=10) == [
            ChannelActivity(SIBLING_CHANNEL, "random", 1),
            ChannelActivity(FOREIGN_CHANNEL, "elsewhere", 1),
        ]
        top = await archive_reads.channel_activity(reads, Scope(guild=GUILD), limit=1)
        assert top == [ChannelActivity(CHANNEL, "general", len(CHANNEL_ORDER))]

    async def test_recent_messages_are_messages_with_the_author_in_scope(
        self, reads: AsyncSession
    ) -> None:
        page = await archive_reads.messages(reads, Scope(author=CAROL), order=NEWEST, limit=5)
        assert _ids(page) == [42, 43]


@in_module_loop
class TestActivity:
    async def test_monthly_across_a_month_and_a_year_boundary(self, reads: AsyncSession) -> None:
        buckets = await archive_reads.activity(reads, Scope(), period=Period.MONTH)
        # Message 33 is posted at 00:25 on 1 February; message 43 on 31 December 2023.
        assert buckets == [
            ActivityBucket(date(2023, 12, 1), 1),
            ActivityBucket(date(2024, 1, 1), len(SEED_MESSAGES) - 2),
            ActivityBucket(date(2024, 2, 1), 1),
        ]

    async def test_weekly_buckets_start_on_monday(self, reads: AsyncSession) -> None:
        buckets = await archive_reads.activity(reads, Scope(), period=Period.WEEK)
        # 31 December 2023 is a Sunday; 31 January and 1 February 2024 share a week.
        assert buckets == [
            ActivityBucket(date(2023, 12, 25), 1),
            ActivityBucket(date(2024, 1, 29), len(SEED_MESSAGES) - 1),
        ]

    async def test_scope(self, reads: AsyncSession) -> None:
        buckets = await archive_reads.activity(reads, Scope(guild=OTHER_GUILD), period=Period.MONTH)
        assert buckets == [ActivityBucket(date(2024, 1, 1), 3)]

    async def test_an_aware_since_behaves_like_its_naive_utc_equivalent(
        self, reads: AsyncSession
    ) -> None:
        naive = datetime(2024, 2, 1, 0, 0, 0)
        aware = naive.replace(tzinfo=UTC).astimezone(timezone(timedelta(hours=9)))
        by_naive = await archive_reads.activity(reads, Scope(), period=Period.MONTH, since=naive)
        by_aware = await archive_reads.activity(reads, Scope(), period=Period.MONTH, since=aware)
        assert by_naive == by_aware == [ActivityBucket(date(2024, 2, 1), 1)]


@in_module_loop
class TestTopChannels:
    async def test_ranked_by_the_ingest_counter_with_an_id_tie_break(
        self, reads: AsyncSession
    ) -> None:
        # "news" holds no messages but its counter says 4: the counter is what ranks.
        assert await archive_reads.top_channels(reads, GUILD, limit=10) == [
            TopChannel(CHANNEL, "general", 9),
            TopChannel(SIBLING_CHANNEL, "random", 4),
            TopChannel(QUIET_CHANNEL, "news", 4),
        ]

    async def test_guild_scope_and_limit(self, reads: AsyncSession) -> None:
        assert await archive_reads.top_channels(reads, OTHER_GUILD, limit=10) == [
            TopChannel(FOREIGN_CHANNEL, "elsewhere", 2)
        ]
        assert await archive_reads.top_channels(reads, GUILD, limit=1) == [
            TopChannel(CHANNEL, "general", 9)
        ]
        assert await archive_reads.top_channels(reads, EMPTY_GUILD, limit=10) == []


def test_top_channels_names_its_source_counter() -> None:
    assert "Channel.message_count" in (archive_reads.top_channels.__doc__ or "")


# --- dialects ------------------------------------------------------------------------------


@in_module_loop
async def test_every_read_compiles_for_sqlite_and_postgresql(reads: AsyncSession) -> None:
    """Every statement the reads emit compiles on both dialects the module targets."""
    emitted: list[Any] = []

    def capture(state: Any) -> None:
        emitted.append(state.statement)

    event.listen(reads.sync_session, "do_orm_execute", capture)
    try:
        scope = Scope(guild=GUILD, channel=CHANNEL, author=ALICE)
        await archive_reads.messages(
            reads,
            scope,
            order=NEWEST,
            limit=1,
            before=8,
            after=1,
            text="a",
            has=Has.IMAGE,
            since=T0,
            until=T0 + timedelta(days=1),
        )
        await archive_reads.messages(reads, scope, order=OLDEST, limit=1, has=Has.LINK)
        await archive_reads.attachments(reads, scope, kind=MediaKind.IMAGE, limit=1)
        await archive_reads.authors(reads, scope, sort=AuthorSort.RECENT, limit=1, name="a")
        await archive_reads.guilds(reads)
        await archive_reads.guild(reads, GUILD)
        await archive_reads.guild_channels(reads, GUILD)
        await archive_reads.guild_counts(reads, [GUILD])
        await archive_reads.user(reads, ALICE)
        await archive_reads.summary(reads, scope)
        await archive_reads.channel_activity(reads, scope, limit=1)
        await archive_reads.reactions(reads, scope, limit=1)
        await archive_reads.activity(reads, scope, period=Period.WEEK, since=T0)
        await archive_reads.top_channels(reads, GUILD, limit=1)
    finally:
        event.remove(reads.sync_session, "do_orm_execute", capture)

    assert len(emitted) > 15
    for statement in emitted:
        for dialect in (sqlite.dialect(), postgresql.dialect()):
            compiled = str(statement.compile(dialect=dialect))
            assert compiled
        assert "strftime" not in str(statement.compile(dialect=postgresql.dialect()))


def test_no_read_side_module_calls_strftime_in_sql() -> None:
    from wumpus_archiver.api.routes import gallery, guilds, messages, search, stats, users

    for module in (archive_reads, gallery, guilds, messages, search, stats, users):
        assert "func.strftime" not in Path(module.__file__).read_text(), module.__name__
