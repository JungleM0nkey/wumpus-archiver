"""Tests for search inputs on the API: case-insensitive matching and LIKE-wildcard escaping.

Also covers ``/api/search`` without ``q``, which lists an author's newest messages.

Covers ``/api/gifs``, ``/api/gifs/random``, ``/api/search`` and
``/api/guilds/{guild_id}/users`` against SQLite (the default database). The unit tests for
the LIKE escaping live with archive reads in ``tests/test_archive_reads.py``.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database

GUILD_ID = 1
CHANNEL_ID = 10

# gif_index is not part of Base.metadata (the gifs routes expect it to be created outside of
# create_tables), so the tests create a minimal stand-in with the columns the routes select.
GIF_INDEX_DDL = """
CREATE TABLE gif_index (
    id INTEGER PRIMARY KEY,
    content_hash TEXT,
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    width INTEGER,
    height INTEGER,
    local_path TEXT,
    url TEXT NOT NULL,
    proxy_url TEXT,
    usage_count INTEGER,
    last_used TEXT,
    channel_id INTEGER
)
"""

GIF_INSERT = """
INSERT INTO gif_index (
    id, content_hash, filename, size, width, height, local_path, url, proxy_url,
    usage_count, last_used, channel_id
) VALUES (
    :id, :content_hash, :filename, 1024, 100, 100, NULL, :url, NULL, 1,
    '2024-01-01T00:00:00', :channel_id
)
"""

# (id, filename). The decoys are chosen so wildcard-interpreted queries match them:
# "100X_real.gif" matches an unescaped "100%_real"; "abc.gif" matches an unescaped "_".
GIF_FILENAMES: list[tuple[int, str]] = [
    (1, "100%_real.gif"),
    (2, "abc.gif"),
    (3, "Dancing_Cat.GIF"),
    (4, "100X_real.gif"),
    (5, "back\\slash.gif"),
]

# (id, content)
MESSAGES: list[tuple[int, str]] = [
    (101, "100% sure about this"),
    (102, "plain message"),
    (103, "snake_case name"),
    (104, "back\\slash path"),
    (105, "Hello World"),
]

# (id, username, global_name)
USERS: list[tuple[int, str, str | None]] = [
    (201, "plain", "Plain Jane"),
    (202, "under_score", None),
    (203, "pct", "100% Bob"),
    (204, "back\\slash", None),
]


@pytest.fixture
async def seeded_db(database: Database) -> Database:
    """Database with a guild, channel, users, messages and a minimal gif_index table."""
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(Guild(id=GUILD_ID, name="Guild"))
        session.add(Channel(id=CHANNEL_ID, guild_id=GUILD_ID, name="general", type=0))
        for user_id, username, global_name in USERS:
            session.add(User(id=user_id, username=username, global_name=global_name))
        for message_id, content in MESSAGES:
            session.add(
                Message(
                    id=message_id,
                    channel_id=CHANNEL_ID,
                    content=content,
                    clean_content=content,
                    created_at=now,
                    scraped_at=now,
                )
            )
        # Every user posts once so they appear in the guild user listing.
        for index, (user_id, _, _) in enumerate(USERS):
            session.add(
                Message(
                    id=900 + index,
                    author_id=user_id,
                    channel_id=CHANNEL_ID,
                    content="hi",
                    clean_content="hi",
                    created_at=now,
                    scraped_at=now,
                )
            )

    async with database.session() as session:
        await session.execute(text(GIF_INDEX_DDL))
        for gif_id, filename in GIF_FILENAMES:
            await session.execute(
                text(GIF_INSERT),
                {
                    "id": gif_id,
                    "content_hash": f"hash{gif_id}",
                    "filename": filename,
                    "url": f"https://cdn.example.test/{gif_id}.gif",
                    "channel_id": CHANNEL_ID,
                },
            )
    return database


@pytest.fixture(autouse=True)
async def _seeded(seeded_db: Database) -> None:
    """Every test here runs the shared ``client`` over the seeded database."""


def _gif_ids(payload: dict[str, Any]) -> set[str]:
    return {gif["id"] for gif in payload["gifs"]}


def _message_ids(payload: dict[str, Any]) -> set[str]:
    return {result["message"]["id"] for result in payload["results"]}


def _user_ids(payload: dict[str, Any]) -> set[str]:
    return {user["id"] for user in payload["users"]}


class TestGifSearch:
    """Tests for GET /api/gifs?q=."""

    async def test_no_query_returns_all(self, client: AsyncClient) -> None:
        """Test listing without q still works."""
        response = await client.get("/api/gifs")
        assert response.status_code == 200
        assert response.json()["total"] == len(GIF_FILENAMES)

    async def test_query_does_not_error_on_sqlite(self, client: AsyncClient) -> None:
        """Test that q works on SQLite (ILIKE is not valid SQLite syntax)."""
        response = await client.get("/api/gifs", params={"q": "abc"})
        assert response.status_code == 200
        payload = response.json()
        assert _gif_ids(payload) == {"2"}
        assert payload["total"] == 1

    @pytest.mark.parametrize("q", ["dancing", "DANCING", "cat.gif", "Dancing_Cat.GIF"])
    async def test_match_is_case_insensitive(self, client: AsyncClient, q: str) -> None:
        """Test that filenames match regardless of case."""
        response = await client.get("/api/gifs", params={"q": q})
        assert response.status_code == 200
        assert _gif_ids(response.json()) == {"3"}

    @pytest.mark.parametrize(
        ("q", "expected_ids"),
        [
            ("%", {"1"}),
            ("_", {"1", "3", "4"}),
            ("100%_real", {"1"}),
            ("_%_%", set()),
            ("\\", {"5"}),
            ("back\\slash", {"5"}),
            ("\\%", set()),
            ("%%", set()),
        ],
    )
    async def test_wildcards_match_literally(
        self, client: AsyncClient, q: str, expected_ids: set[str]
    ) -> None:
        """Test that %, _ and backslash in q only match those literal characters."""
        response = await client.get("/api/gifs", params={"q": q})
        assert response.status_code == 200
        payload = response.json()
        assert _gif_ids(payload) == expected_ids
        assert payload["total"] == len(expected_ids)

    async def test_query_combines_with_channel_filter(self, client: AsyncClient) -> None:
        """Test that the escaped query composes with the other filters."""
        response = await client.get("/api/gifs", params={"q": "%", "channel_id": CHANNEL_ID})
        assert response.status_code == 200
        assert _gif_ids(response.json()) == {"1"}

        response = await client.get("/api/gifs", params={"q": "%", "channel_id": CHANNEL_ID + 1})
        assert response.status_code == 200
        assert _gif_ids(response.json()) == set()


class TestRandomGif:
    """Tests for GET /api/gifs/random?q=."""

    async def test_random_with_query(self, client: AsyncClient) -> None:
        """Test that random works with q on SQLite and matches case-insensitively."""
        response = await client.get("/api/gifs/random", params={"q": "ABC"})
        assert response.status_code == 200
        assert response.json()["id"] == "2"

    async def test_random_without_query(self, client: AsyncClient) -> None:
        """Test that random without q returns one of the seeded GIFs."""
        response = await client.get("/api/gifs/random")
        assert response.status_code == 200
        assert response.json()["id"] in {str(gif_id) for gif_id, _ in GIF_FILENAMES}

    @pytest.mark.parametrize(("q", "expected_id"), [("%", "1"), ("100%_real", "1"), ("\\", "5")])
    async def test_random_wildcards_match_literally(
        self, client: AsyncClient, q: str, expected_id: str
    ) -> None:
        """Test that wildcards in q are literal; repeat to defeat random ordering."""
        for _ in range(10):
            response = await client.get("/api/gifs/random", params={"q": q})
            assert response.status_code == 200
            assert response.json()["id"] == expected_id

    @pytest.mark.parametrize("q", ["_%_%", "%%", "nosuchgif"])
    async def test_random_no_match_is_404(self, client: AsyncClient, q: str) -> None:
        """Test that a query with no literal match returns 404, not an error."""
        response = await client.get("/api/gifs/random", params={"q": q})
        assert response.status_code == 404


class TestMessageSearch:
    """Tests for GET /api/search?q=."""

    async def test_case_insensitive_match(self, client: AsyncClient) -> None:
        """Test that message search is case-insensitive."""
        response = await client.get("/api/search", params={"q": "HELLO"})
        assert response.status_code == 200
        payload = response.json()
        assert _message_ids(payload) == {"105"}
        assert payload["total"] == 1

    @pytest.mark.parametrize(
        ("q", "expected_ids"),
        [
            ("%", {"101"}),
            ("_", {"103"}),
            ("100%", {"101"}),
            ("_%_%", set()),
            ("\\", {"104"}),
            ("back\\slash", {"104"}),
        ],
    )
    async def test_wildcards_match_literally(
        self, client: AsyncClient, q: str, expected_ids: set[str]
    ) -> None:
        """Test that wildcards only match literal characters in both results and total."""
        response = await client.get("/api/search", params={"q": q})
        assert response.status_code == 200
        payload = response.json()
        assert _message_ids(payload) == expected_ids
        # The count query is built separately from the results query.
        assert payload["total"] == len(expected_ids)
        assert payload["query"] == q

    async def test_wildcard_with_channel_and_guild_filters(self, client: AsyncClient) -> None:
        """Test that the escaped query composes with the channel and guild filters."""
        for params in ({"channel_id": CHANNEL_ID}, {"guild_id": GUILD_ID}):
            response = await client.get("/api/search", params={"q": "%", **params})
            assert response.status_code == 200
            payload = response.json()
            assert _message_ids(payload) == {"101"}
            assert payload["total"] == 1

        response = await client.get("/api/search", params={"q": "%", "channel_id": CHANNEL_ID + 1})
        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_results_carry_their_channel_name(
        self, client: AsyncClient, statements: list[str]
    ) -> None:
        """Test that each result names its channel, joined into the search page."""
        response = await client.get("/api/search", params={"q": "HELLO"})
        assert response.status_code == 200
        assert [r["channel_name"] for r in response.json()["results"]] == ["general"]
        assert sum("JOIN channels" in statement for statement in statements) == 1

    async def test_author_filter_narrows_the_total_too(self, client: AsyncClient) -> None:
        """Test that the total counts only the author's matches, like the results."""
        response = await client.get("/api/search", params={"q": "hi", "author_id": 201})
        assert response.status_code == 200
        payload = response.json()
        assert _message_ids(payload) == {"900"}
        assert payload["total"] == 1

    @pytest.mark.parametrize("param", ["guild_id", "channel_id", "author_id"])
    async def test_a_zero_id_is_no_filter(self, client: AsyncClient, param: str) -> None:
        """Test that an id of 0 means the filter is absent, as it always has."""
        unfiltered = await client.get("/api/search", params={"q": "%"})
        response = await client.get("/api/search", params={"q": "%", param: 0})
        assert response.status_code == 200
        assert response.json() == unfiltered.json()
        assert response.json()["total"] == 1

    async def test_a_channel_outside_the_guild_matches_nothing(self, client: AsyncClient) -> None:
        """Test that guild and channel apply together rather than the channel winning."""
        response = await client.get(
            "/api/search", params={"q": "%", "guild_id": GUILD_ID + 1, "channel_id": CHANNEL_ID}
        )
        assert response.status_code == 200
        assert response.json() == {"results": [], "total": 0, "query": "%"}


class TestAuthorMessages:
    """Tests for GET /api/search?author_id= without q: an author's newest messages."""

    @pytest.fixture(autouse=True)
    async def _older_messages(self, seeded_db: Database) -> None:
        """User 202 also posted three older messages, an hour apart."""
        async with seeded_db.session() as session:
            for index, hour in enumerate((1, 3, 2)):
                session.add(
                    Message(
                        id=950 + index,
                        author_id=202,
                        channel_id=CHANNEL_ID,
                        content=f"older {hour}",
                        clean_content=f"older {hour}",
                        created_at=datetime(2024, 1, 1, hour, tzinfo=UTC),
                        scraped_at=datetime.now(UTC),
                    )
                )

    async def test_lists_the_authors_messages_newest_first(self, client: AsyncClient) -> None:
        """Test that without q the page is every message of the author, newest first."""
        response = await client.get("/api/search", params={"author_id": 202})
        assert response.status_code == 200
        payload = response.json()
        contents = [r["message"]["content"] for r in payload["results"]]
        assert contents == ["hi", "older 3", "older 2", "older 1"]
        assert {r["message"]["author"]["id"] for r in payload["results"]} == {"202"}
        assert (payload["total"], payload["query"]) == (4, None)

    async def test_limit_keeps_the_newest_and_the_whole_total(self, client: AsyncClient) -> None:
        """Test that a limited page holds the newest messages and the total counts them all."""
        response = await client.get("/api/search", params={"author_id": 202, "limit": 2})
        assert response.status_code == 200
        payload = response.json()
        assert [r["message"]["id"] for r in payload["results"]] == ["901", "951"]
        assert payload["total"] == 4

    async def test_composes_with_guild_and_channel(self, client: AsyncClient) -> None:
        """Test that the author's messages stay scoped by guild and channel."""
        params = {"author_id": 202, "guild_id": GUILD_ID, "channel_id": CHANNEL_ID}
        response = await client.get("/api/search", params=params)
        assert response.json()["total"] == 4
        response = await client.get("/api/search", params={"author_id": 202, "guild_id": 2})
        assert response.status_code == 200
        assert response.json() == {"results": [], "total": 0, "query": None}

    @pytest.mark.parametrize(
        "params", [{}, {"guild_id": GUILD_ID}, {"author_id": 0}, {"q": "", "author_id": 202}]
    )
    async def test_q_is_required_without_an_author(
        self, client: AsyncClient, params: dict[str, Any]
    ) -> None:
        """Test that neither q nor an author, or an empty q, is still a 422."""
        response = await client.get("/api/search", params=params)
        assert response.status_code == 422


class TestUserSearch:
    """Tests for GET /api/guilds/{guild_id}/users?q=."""

    async def test_no_query_lists_all_users(self, client: AsyncClient) -> None:
        """Test listing guild users without q."""
        response = await client.get(f"/api/guilds/{GUILD_ID}/users")
        assert response.status_code == 200
        assert response.json()["total"] == len(USERS)

    async def test_case_insensitive_match_on_global_name(self, client: AsyncClient) -> None:
        """Test that q matches the global name case-insensitively."""
        response = await client.get(f"/api/guilds/{GUILD_ID}/users", params={"q": "JANE"})
        assert response.status_code == 200
        assert _user_ids(response.json()) == {"201"}

    @pytest.mark.parametrize(
        ("q", "expected_ids"),
        [
            ("_", {"202"}),
            ("%", {"203"}),
            ("100%", {"203"}),
            ("_%_%", set()),
            ("\\", {"204"}),
            ("back\\slash", {"204"}),
        ],
    )
    async def test_wildcards_match_literally(
        self, client: AsyncClient, q: str, expected_ids: set[str]
    ) -> None:
        """Test that wildcards in q only match literal characters in username/global_name."""
        response = await client.get(f"/api/guilds/{GUILD_ID}/users", params={"q": q})
        assert response.status_code == 200
        payload = response.json()
        assert _user_ids(payload) == expected_ids
        assert payload["total"] == len(expected_ids)
