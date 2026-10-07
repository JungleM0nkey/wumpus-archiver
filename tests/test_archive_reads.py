"""Direct tests for archive reads (``wumpus_archiver.storage.archive_reads``)."""

import ast
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import (
    Has,
    MediaKind,
    Order,
    Page,
    Scope,
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
CHANNEL = 10
SIBLING_CHANNEL = 11
FOREIGN_CHANNEL = 20
ALICE = 100
BOB = 101
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
    (40, FOREIGN_CHANNEL, BOB, 5, "foreign"),
]
# Channel 10 in time order, (created_at, id) ascending.
CHANNEL_ORDER = [1, 2, 3, 4, 5, 6, 7, 9, 8]

# (id, message, content_type)
SEED_ATTACHMENTS: list[tuple[int, int, str | None]] = [
    (501, 3, "image/png"),
    (502, 4, "video/mp4"),
    (503, 7, "application/pdf"),
]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def archive(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[Database]:
    """One seeded archive shared by every test in this file."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('reads') / 'archive.db'}")
    await db.connect()
    await db.create_tables()
    async with db.session() as session:
        session.add_all([Guild(id=GUILD, name="one"), Guild(id=OTHER_GUILD, name="two")])
        session.add_all(
            [
                Channel(id=CHANNEL, guild_id=GUILD, name="general", type=0),
                Channel(id=SIBLING_CHANNEL, guild_id=GUILD, name="random", type=0),
                Channel(id=FOREIGN_CHANNEL, guild_id=OTHER_GUILD, name="elsewhere", type=0),
            ]
        )
        session.add_all([User(id=ALICE, username="alice"), User(id=BOB, username="bob")])
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
        assert [a.id for a in third.attachments] == [501]
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
        assert set(_ids(page)) == set(CHANNEL_ORDER) | {30}

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
