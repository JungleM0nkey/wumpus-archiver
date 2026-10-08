"""The user, guild users and profile routes over a seeded archive."""

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest
from httpx import AsyncClient

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database

NOW = datetime.now(UTC).replace(tzinfo=None, microsecond=0)

# (id, channel, author, days ago, content)
MESSAGES = [
    (1, 10, 100, 800, "too old for the chart"),
    (2, 10, 100, 40, "hello"),
    (3, 10, 100, 39, "hello again"),
    (4, 11, 100, 5, "elsewhere in the guild"),
    (5, 20, 100, 4, "another guild"),
    (6, 10, 101, 3, "bob"),
]


@pytest.fixture(autouse=True)
async def seeded(database: Database) -> None:
    async with database.session() as session:
        session.add_all([Guild(id=1, name="one"), Guild(id=2, name="two")])
        session.add_all(
            [
                Channel(id=10, guild_id=1, name="general", type=0),
                Channel(id=11, guild_id=1, name="random", type=0),
                Channel(id=20, guild_id=2, name="elsewhere", type=0),
            ]
        )
        session.add_all(
            [
                User(id=100, username="alice", global_name="Alice"),
                User(id=101, username="bob"),
            ]
        )
        for message_id, channel_id, author_id, days, content in MESSAGES:
            session.add(
                Message(
                    id=message_id,
                    channel_id=channel_id,
                    author_id=author_id,
                    content=content,
                    clean_content=content,
                    created_at=NOW - timedelta(days=days),
                    scraped_at=NOW,
                )
            )
        session.add(
            Attachment(
                id=900, message_id=2, filename="a.png", content_type="image/png", size=1, url="u"
            )
        )
        session.add_all(
            [
                Reaction(message_id=2, emoji_name="thumbs", count=4),
                Reaction(message_id=5, emoji_name="party", count=2),
                Reaction(message_id=3, emoji_name=None, count=1),
            ]
        )


def _month(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m")


async def test_user(client: AsyncClient) -> None:
    response = await client.get("/api/users/100")
    assert response.json()["display_name"] == "Alice"


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("messages", ["100", "101"]),
        ("name", ["100", "101"]),
        ("recent", ["101", "100"]),
        ("bogus", ["100", "101"]),
    ],
)
async def test_guild_users_sorts(client: AsyncClient, sort: str, expected: list[str]) -> None:
    response = await client.get("/api/guilds/1/users", params={"sort": sort})
    payload = response.json()
    assert [u["id"] for u in payload["users"]] == expected
    assert (payload["total"], payload["has_more"]) == (2, False)
    alice = next(u for u in payload["users"] if u["id"] == "100")
    assert alice["message_count"] == 4
    assert alice["first_seen"] == (NOW - timedelta(days=800)).isoformat()


async def test_profile_across_the_archive(client: AsyncClient) -> None:
    payload = (await client.get("/api/users/100/profile")).json()
    contents = [m[4] for m in MESSAGES if m[2] == 100]
    assert payload["total_messages"] == 5
    assert payload["total_attachments"] == 1
    assert payload["total_reactions_received"] == 7
    assert payload["active_channels"] == 3
    assert payload["avg_message_length"] == round(sum(map(len, contents)) / len(contents), 1)
    assert payload["first_message_at"] == (NOW - timedelta(days=800)).isoformat()
    assert [c["channel_id"] for c in payload["top_channels"]][0] == "10"
    assert payload["top_reactions_received"] == [
        {"emoji": "thumbs", "count": 4},
        {"emoji": "party", "count": 2},
        {"emoji": "?", "count": 1},
    ]
    months = {m["period"]: m["count"] for m in payload["monthly_activity"]}
    assert _month(800) not in months
    assert sum(months.values()) == 4
    assert all(
        m["label"] == datetime.strptime(m["period"], "%Y-%m").strftime("%b %Y")
        for m in payload["monthly_activity"]
    )


async def test_profile_scoped_to_a_guild(client: AsyncClient) -> None:
    payload = (await client.get("/api/users/100/profile", params={"guild_id": 1})).json()
    assert (payload["total_messages"], payload["active_channels"]) == (4, 2)
    assert payload["total_reactions_received"] == 5
    assert [c["channel_id"] for c in payload["top_channels"]] == ["10", "11"]


async def test_guild_users_sort_by_the_shown_name_ignoring_case(
    client: AsyncClient, database: Database
) -> None:
    # The shown name is the global name, else the username. By code point "BEN" and
    # "Zoe" would sort before "alice".
    async with database.session() as session:
        session.add_all(
            [User(id=102, username="Zoe", global_name="ann"), User(id=103, username="BEN")]
        )
        for message_id, author_id in [(7, 102), (8, 103)]:
            session.add(
                Message(
                    id=message_id,
                    channel_id=20,
                    author_id=author_id,
                    content="hi",
                    clean_content="hi",
                    created_at=NOW,
                    scraped_at=NOW,
                )
            )
    payload = (await client.get("/api/guilds/2/users", params={"sort": "name"})).json()
    assert [u["display_name"] for u in payload["users"]] == ["Alice", "ann", "BEN"]


def _monday(days_ago: int) -> date:
    on = (NOW - timedelta(days=days_ago)).date()
    return on - timedelta(days=on.weekday())


def _weeks(payload: dict[str, Any]) -> dict[date, int]:
    """The profile's weekly activity, checked to be 52 consecutive weeks from a Monday."""
    weeks = {date.fromisoformat(w["week"]): w["count"] for w in payload["weekly_activity"]}
    starts = list(weeks)
    assert len(starts) == 52
    assert starts[0].weekday() == 0
    assert all(b - a == timedelta(weeks=1) for a, b in pairwise(starts))
    return weeks


@pytest.mark.parametrize(
    ("params", "last_message_days_ago", "in_window"),
    [
        # Messages 40, 39, 5 and 4 days ago; the one 800 days ago is outside the window.
        ({}, 4, 4),
        # The guild holds the ones 40, 39 and 5 days ago.
        ({"guild_id": 1}, 5, 3),
    ],
)
async def test_profile_weekly_activity_covers_52_weeks_and_sums_to_the_messages_in_them(
    client: AsyncClient, params: dict[str, int], last_message_days_ago: int, in_window: int
) -> None:
    payload = (await client.get("/api/users/100/profile", params=params)).json()
    weeks = _weeks(payload)
    assert list(weeks)[-1] == _monday(last_message_days_ago)
    assert sum(weeks.values()) == in_window
    assert weeks[_monday(40)] + weeks[_monday(39)] >= 2


async def test_profile_weekly_activity_ends_with_an_old_last_message(
    client: AsyncClient, database: Database
) -> None:
    # An archive is a copy of the past: the window ends with the author's last message,
    # not today, and counts only what falls in its 52 weeks.
    async with database.session() as session:
        session.add(User(id=102, username="carol"))
        for message_id, days in [(7, 400), (8, 403), (9, 400 + 52 * 7)]:
            session.add(
                Message(
                    id=message_id,
                    channel_id=10,
                    author_id=102,
                    content="old",
                    clean_content="old",
                    created_at=NOW - timedelta(days=days),
                    scraped_at=NOW,
                )
            )
    payload = (await client.get("/api/users/102/profile")).json()
    weeks = _weeks(payload)
    assert list(weeks)[-1] == _monday(400)
    assert sum(weeks.values()) == 2
    assert payload["total_messages"] == 3


async def test_profile_weekly_activity_without_messages_is_52_empty_weeks_to_this_one(
    client: AsyncClient, database: Database
) -> None:
    async with database.session() as session:
        session.add(User(id=102, username="quiet"))
    weeks = _weeks((await client.get("/api/users/102/profile")).json())
    today = datetime.now(UTC).date()
    assert list(weeks)[-1] == today - timedelta(days=today.weekday())
    assert set(weeks.values()) == {0}
