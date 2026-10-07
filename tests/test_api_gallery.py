"""The gallery routes over a seeded archive: their parameters and defaults."""

from datetime import datetime

import pytest
from httpx import AsyncClient

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database

# (attachment id, message id, content type); message n is posted on day n.
ATTACHMENTS = [
    (501, 1, "image/png"),
    (502, 2, "image/gif"),
    (503, 3, "video/mp4"),
    (504, 4, "image/jpeg"),
]


@pytest.fixture(autouse=True)
async def seeded(database: Database) -> None:
    async with database.session() as session:
        session.add_all([Guild(id=1, name="one"), Guild(id=2, name="two")])
        session.add_all(
            [
                Channel(id=10, guild_id=1, name="general", type=0),
                Channel(id=20, guild_id=2, name="elsewhere", type=0),
            ]
        )
        session.add(User(id=100, username="alice", global_name="Alice"))
        for message_id in range(1, 5):
            session.add(
                Message(
                    id=message_id,
                    channel_id=10,
                    author_id=100,
                    created_at=datetime(2024, 1, message_id),
                    scraped_at=datetime(2024, 1, 1),
                )
            )
        for attachment_id, message_id, content_type in ATTACHMENTS:
            session.add(
                Attachment(
                    id=attachment_id,
                    message_id=message_id,
                    filename=f"{attachment_id}",
                    content_type=content_type,
                    size=1,
                    url=f"https://cdn.example.test/{attachment_id}",
                )
            )


def _ids(payload: dict[str, object]) -> list[str]:
    return [a["id"] for a in payload["attachments"]]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        (None, ["504", "502", "501"]),
        ("image", ["504", "502", "501"]),
        ("gif", ["502"]),
        ("video", ["503"]),
        ("anything else", ["504", "502", "501"]),
    ],
)
async def test_guild_gallery_content_type(
    client: AsyncClient, content_type: str | None, expected: list[str]
) -> None:
    params = {"content_type": content_type} if content_type else {}
    response = await client.get("/api/guilds/1/gallery", params=params)
    assert response.status_code == 200
    payload = response.json()
    assert _ids(payload) == expected
    assert payload["total"] == len(expected)


async def test_guild_gallery_paging_and_context(client: AsyncClient) -> None:
    response = await client.get("/api/guilds/1/gallery", params={"limit": 2, "offset": 1})
    payload = response.json()
    assert (_ids(payload), payload["total"], payload["has_more"]) == (["502", "501"], 3, False)
    first = payload["attachments"][0]
    assert (first["author_name"], first["channel_name"], first["channel_id"]) == (
        "Alice",
        "general",
        "10",
    )


async def test_guild_gallery_with_a_channel_of_another_guild_is_empty(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/guilds/2/gallery", params={"channel_id": 10})
    assert response.json() == {"attachments": [], "total": 0, "has_more": False, "offset": 0}


@pytest.mark.parametrize("path", ["/api/guilds/1/gallery", "/api/guilds/1/gallery/timeline"])
async def test_a_zero_channel_id_is_no_filter(client: AsyncClient, path: str) -> None:
    unfiltered = await client.get(path)
    response = await client.get(path, params={"channel_id": 0})
    assert response.status_code == 200
    assert response.json() == unfiltered.json()
    assert response.json()["total"] == 3


async def test_channel_gallery_names_the_channel(client: AsyncClient) -> None:
    response = await client.get("/api/channels/10/gallery")
    payload = response.json()
    assert _ids(payload) == ["504", "502", "501"]
    assert {a["channel_name"] for a in payload["attachments"]} == {"general"}


async def test_timeline_groups_the_page(client: AsyncClient) -> None:
    response = await client.get("/api/guilds/1/gallery/timeline", params={"group_by": "year"})
    payload = response.json()
    assert [(g["period"], g["count"]) for g in payload["groups"]] == [("2024", 3)]
    assert payload["total"] == 3
