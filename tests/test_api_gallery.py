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

# (attachment id, message id, content type); message n is posted on day n, messages 1
# and 2 by Alice, 3 and 4 by Bob.
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
        session.add(User(id=200, username="bob", global_name="Bob"))
        for message_id in range(1, 5):
            session.add(
                Message(
                    id=message_id,
                    channel_id=10,
                    author_id=100 if message_id <= 2 else 200,
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


# ── The gallery timeline's filters, behind the Media screen (#62) ──────────────

TIMELINE = "/api/guilds/1/gallery/timeline"


def _timeline_ids(payload: dict[str, object]) -> list[str]:
    groups = payload["groups"]
    return [a["id"] for g in groups for a in g["attachments"]]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        (None, ["504", "502", "501"]),
        ("image", ["504", "502", "501"]),
        ("gif", ["502"]),
        ("video", ["503"]),
        ("media", ["504", "503", "502", "501"]),
    ],
)
async def test_timeline_content_type(
    client: AsyncClient, content_type: str | None, expected: list[str]
) -> None:
    params = {"content_type": content_type} if content_type else {}
    response = await client.get(TIMELINE, params=params)
    assert response.status_code == 200
    payload = response.json()
    assert _timeline_ids(payload) == expected
    assert payload["total"] == len(expected)


async def test_timeline_video_filter_returns_only_videos(client: AsyncClient) -> None:
    payload = (await client.get(TIMELINE, params={"content_type": "video"})).json()
    kinds = {a["content_type"] for g in payload["groups"] for a in g["attachments"]}
    assert (kinds, payload["total"], payload["has_more"]) == ({"video/mp4"}, 1, False)


async def test_timeline_rejects_an_unknown_content_type(client: AsyncClient) -> None:
    response = await client.get(TIMELINE, params={"content_type": "audio"})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("author_id", "content_type", "expected"),
    [
        (100, "media", ["502", "501"]),
        (200, "media", ["504", "503"]),
        (200, "image", ["504"]),
        (100, "gif", ["502"]),
        (200, "gif", []),
        (300, "media", []),
    ],
)
async def test_timeline_author_filter(
    client: AsyncClient, author_id: int, content_type: str, expected: list[str]
) -> None:
    params = {"author_id": author_id, "content_type": content_type}
    payload = (await client.get(TIMELINE, params=params)).json()
    assert _timeline_ids(payload) == expected
    assert payload["total"] == len(expected)


async def test_timeline_author_filter_shows_only_that_author(client: AsyncClient) -> None:
    params = {"author_id": 200, "content_type": "media"}
    payload = (await client.get(TIMELINE, params=params)).json()
    assert {a["author_name"] for g in payload["groups"] for a in g["attachments"]} == {"Bob"}


async def test_timeline_filters_combine_and_the_total_ignores_paging(client: AsyncClient) -> None:
    params = {"content_type": "media", "author_id": 100, "channel_id": 10, "limit": 1}
    first = (await client.get(TIMELINE, params=params)).json()
    assert (_timeline_ids(first), first["total"], first["has_more"]) == (["502"], 2, True)
    second = (await client.get(TIMELINE, params={**params, "offset": 1})).json()
    assert (_timeline_ids(second), second["total"], second["has_more"]) == (["501"], 2, False)


async def test_timeline_with_a_channel_of_another_guild_is_empty(client: AsyncClient) -> None:
    params = {"channel_id": 10, "content_type": "media"}
    payload = (await client.get("/api/guilds/2/gallery/timeline", params=params)).json()
    assert (payload["groups"], payload["total"]) == ([], 0)


async def test_a_zero_author_id_is_no_filter(client: AsyncClient) -> None:
    unfiltered = await client.get(TIMELINE, params={"content_type": "media"})
    response = await client.get(TIMELINE, params={"content_type": "media", "author_id": 0})
    assert response.json() == unfiltered.json()


@pytest.mark.parametrize(
    ("order", "expected"),
    [("newest", ["504", "503", "502", "501"]), ("oldest", ["501", "502", "503", "504"])],
)
async def test_timeline_order(client: AsyncClient, order: str, expected: list[str]) -> None:
    params = {"content_type": "media", "order": order}
    payload = (await client.get(TIMELINE, params=params)).json()
    assert _timeline_ids(payload) == expected


async def test_a_month_split_across_pages_keeps_its_period_key(client: AsyncClient) -> None:
    """The Media screen merges a period's groups across pages by this key."""
    params = {"content_type": "media", "limit": 2}
    first = (await client.get(TIMELINE, params=params)).json()
    second = (await client.get(TIMELINE, params={**params, "offset": 2})).json()
    groups = [(g["period"], g["label"], g["count"]) for g in first["groups"] + second["groups"]]
    assert groups == [("2024-01", "January 2024", 2), ("2024-01", "January 2024", 2)]
