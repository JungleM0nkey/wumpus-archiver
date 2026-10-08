"""The channel activity route, behind Browse's jump rail (#61)."""

from datetime import datetime

import pytest
from httpx import AsyncClient

from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.storage.database import Database

# (id, channel, created_at). Ids are deliberately not in time order, and 7 and 6 share
# March's first instant: the reader orders by (created_at, id), so 6 comes first.
MESSAGES = [
    (1, 10, datetime(2023, 12, 31, 23, 59)),
    (9, 10, datetime(2024, 1, 2, 8, 0)),
    (2, 10, datetime(2024, 1, 2, 9, 0)),
    (3, 10, datetime(2024, 1, 31, 23, 0)),
    (7, 10, datetime(2024, 3, 1, 0, 0)),
    (6, 10, datetime(2024, 3, 1, 0, 0)),
    (8, 10, datetime(2024, 3, 9, 12, 0)),
    (4, 11, datetime(2023, 11, 5)),
    (5, 20, datetime(2024, 2, 1)),
]


@pytest.fixture(autouse=True)
async def seeded(database: Database) -> None:
    async with database.session() as session:
        session.add_all([Guild(id=1, name="one"), Guild(id=2, name="two")])
        session.add_all(
            [
                Channel(id=10, guild_id=1, name="general", type=0, message_count=7),
                Channel(id=11, guild_id=1, name="random", type=0, message_count=1),
                Channel(id=12, guild_id=1, name="quiet", type=0),
                Channel(id=20, guild_id=2, name="elsewhere", type=0, message_count=1),
            ]
        )
        session.add_all(
            Message(id=message_id, channel_id=channel_id, created_at=at, scraped_at=at)
            for message_id, channel_id, at in MESSAGES
        )


async def test_channel_activity_counts_messages_per_month_with_each_first_message(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/channels/10/activity")
    assert response.status_code == 200
    assert response.json() == {
        "period": "month",
        "buckets": [
            {"start": "2023-12-01", "messages": 1, "first_message_id": "1"},
            {"start": "2024-01-01", "messages": 3, "first_message_id": "9"},
            {"start": "2024-03-01", "messages": 3, "first_message_id": "6"},
        ],
    }


@pytest.mark.parametrize("channel_id", [10, 11, 12, 20])
async def test_channel_activity_sums_to_the_channels_message_total(
    client: AsyncClient, channel_id: int
) -> None:
    activity = (await client.get(f"/api/channels/{channel_id}/activity")).json()
    messages = (await client.get(f"/api/channels/{channel_id}/messages")).json()
    assert sum(b["messages"] for b in activity["buckets"]) == messages["total"]
    expected = sum(1 for _, channel, _ in MESSAGES if channel == channel_id)
    assert messages["total"] == expected


async def test_channel_activity_by_week(client: AsyncClient) -> None:
    payload = (await client.get("/api/channels/10/activity", params={"period": "week"})).json()
    assert payload["period"] == "week"
    # 31 December 2023 is a Sunday, so it closes the week of Monday 25 December.
    assert [(b["start"], b["messages"], b["first_message_id"]) for b in payload["buckets"]] == [
        ("2023-12-25", 1, "1"),
        ("2024-01-01", 2, "9"),
        ("2024-01-29", 1, "3"),
        ("2024-02-26", 2, "6"),
        ("2024-03-04", 1, "8"),
    ]


async def test_channel_activity_issues_three_statements(
    client: AsyncClient, statements: list[str]
) -> None:
    """The channel lookup, the day groups and one read of the first messages: no N+1."""
    assert (await client.get("/api/channels/10/activity")).status_code == 200
    assert len(statements) == 3


async def test_channel_activity_of_an_unknown_channel_is_404(client: AsyncClient) -> None:
    assert (await client.get("/api/channels/99/activity")).status_code == 404
    assert (
        await client.get("/api/channels/10/activity", params={"period": "year"})
    ).status_code == 422
