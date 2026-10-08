"""The smoke archive holds what the portal smoke suite looks for.

The portal suite only sees the archive through a browser; these tests pin the seed
itself through the API, so a change to it fails here first and says why.
"""

import itertools
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from tests.smoke_archive import (
    ALICE_ID,
    ART_ID,
    CAROL_ID,
    GENERAL_ID,
    GUILD_ID,
    HANGOUT_ID,
    LOBBY_ID,
    LURKERS,
    NIGHT_GUILD_ID,
    NIGHT_SCRAPE_ADDED,
    PINNED,
    RANDOM_ID,
    SORTED_APART,
    SORTED_APART_MESSAGES,
    seed_smoke_archive,
    write_attachments,
    write_smoke_archive,
)
from wumpus_archiver.storage.database import Database


@pytest.fixture
def attachments_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "attachments"
    write_attachments(directory)
    return directory


@pytest.fixture(autouse=True)
async def seeded(database: Database) -> None:
    await seed_smoke_archive(database)


async def test_one_guild_with_categories_two_authors_and_the_lurkers(client: AsyncClient) -> None:
    guild = (await client.get(f"/api/guilds/{GUILD_ID}")).json()
    assert [c["name"] for c in guild["channels"] if c["type"] == 4] == ["Text Channels", "Media"]
    stats = (await client.get(f"/api/guilds/{GUILD_ID}/stats")).json()
    totals = (stats["total_messages"], stats["total_users"], stats["total_attachments"])
    authors = 2 + LURKERS + len(SORTED_APART)
    # Four attachments on #art, five on #random for the Media screen (#62).
    assert totals == (12 + LURKERS + SORTED_APART_MESSAGES, authors, 4 + 5)


async def test_a_second_guild_shares_nothing_with_the_first(client: AsyncClient) -> None:
    """The shell's guild switcher smoke tests tell the guilds apart by these totals and names."""
    guilds = (await client.get("/api/guilds")).json()
    assert [(g["id"], g["name"]) for g in guilds] == [
        (str(GUILD_ID), "Smoke Test Guild"),
        (str(NIGHT_GUILD_ID), "Night Owls"),
    ]
    stats = (await client.get(f"/api/guilds/{NIGHT_GUILD_ID}/stats")).json()
    totals = (
        stats["total_channels"],
        stats["total_messages"],
        stats["total_users"],
        stats["total_attachments"],
    )
    assert totals == (3, 5, 2, 1)
    users = (await client.get(f"/api/guilds/{NIGHT_GUILD_ID}/users")).json()["users"]
    assert [u["display_name"] for u in users] == ["Carol", "Dave"]
    assert users[0]["id"] == str(CAROL_ID)


async def test_a_search_scoped_to_a_guild_finds_only_its_messages(client: AsyncClient) -> None:
    async def found(**params: object) -> list[str]:
        search = (await client.get("/api/search", params={"q": "game", **params})).json()
        return sorted(r["message"]["content"] for r in search["results"])

    first, night = ["Anyone up for a game tonight?"], ["Game night is on Friday."]
    assert await found() == sorted(first + night)
    assert await found(guild_id=GUILD_ID) == first
    assert await found(guild_id=NIGHT_GUILD_ID) == night


async def test_the_people_screen_has_a_third_page(client: AsyncClient) -> None:
    """The People screen pages 50 authors at a time; its smoke test clicks Load more twice."""
    params = {"offset": 100, "limit": 50}
    page = (await client.get(f"/api/guilds/{GUILD_ID}/users", params=params)).json()
    assert (len(page["users"]), page["total"], page["has_more"]) == (22, 122, False)


@pytest.mark.parametrize(
    ("sort", "first"),
    [
        ("messages", ["Alice", "Bob", "Zara", "aaron", "Lurker 001"]),
        ("name", ["aaron", "Alice", "Bob", "Lurker 001", "Lurker 002"]),
    ],
)
async def test_people_sorted_by_name_and_by_messages_differ(
    client: AsyncClient, sort: str, first: list[str]
) -> None:
    """The People smoke test sorts both ways and sees the table reorder."""
    params = {"sort": sort, "limit": 5}
    users = (await client.get(f"/api/guilds/{GUILD_ID}/users", params=params)).json()["users"]
    assert [u["display_name"] for u in users] == first


async def test_messages_carry_replies_reactions_and_local_attachments(client: AsyncClient) -> None:
    response = await client.get(f"/api/channels/{ART_ID}/messages")
    messages = response.json()["messages"]
    assert any(m["reference_id"] for m in messages)
    assert any(m["reactions"] for m in messages)
    urls = [a["url"] for m in messages for a in m["attachments"]]
    assert len(urls) == 4
    assert all(url.startswith("/attachments/") for url in urls)
    for url in urls:
        assert (await client.get(url)).status_code == 200


async def test_browse_has_a_voice_channel_to_leave_out(client: AsyncClient) -> None:
    """The Browse smoke tests check the channel pane lists the text channels, not this."""
    guild = (await client.get(f"/api/guilds/{GUILD_ID}")).json()
    voice = [c for c in guild["channels"] if c["type"] == 2]
    assert [(c["id"], c["name"]) for c in voice] == [(str(HANGOUT_ID), "hangout")]
    texts = {c["name"]: c["message_count"] for c in guild["channels"] if c["type"] == 0}
    lobby = LURKERS + SORTED_APART_MESSAGES
    assert texts == {"general": 6, "random": 3, "lobby": lobby, "art": 3}


async def test_search_and_profile_find_the_seeded_text(client: AsyncClient) -> None:
    search = (await client.get("/api/search", params={"q": "hello"})).json()
    assert [r["message"]["content"] for r in search["results"]] == ["The hello world of June."]
    profile = (await client.get(f"/api/users/{ALICE_ID}/profile")).json()
    assert profile["display_name"] == "Alice"


# ── #67 Overview ─────────────────────────────────────────────────────────────


async def test_only_night_owls_has_a_completed_scrape_job(client: AsyncClient) -> None:
    """The Overview's smoke tests show a change on Night Owls' tiles and none on the first's."""
    first = (await client.get(f"/api/guilds/{GUILD_ID}/stats")).json()
    assert first["since_last_scrape"] is None
    night = (await client.get(f"/api/guilds/{NIGHT_GUILD_ID}/stats")).json()
    change = night["since_last_scrape"]
    assert {key: change[key] for key in NIGHT_SCRAPE_ADDED} == NIGHT_SCRAPE_ADDED


async def test_the_most_active_channels_leave_out_the_categories(client: AsyncClient) -> None:
    stats = (await client.get(f"/api/guilds/{GUILD_ID}/stats")).json()
    assert [c["name"] for c in stats["top_channels"]] == ["lobby", "general", "random", "art"]


async def test_the_first_guild_is_active_in_two_months(client: AsyncClient) -> None:
    """The Overview chart's smoke test counts one point per month."""
    activity = (await client.get(f"/api/guilds/{GUILD_ID}/activity")).json()
    assert [b["start"] for b in activity["buckets"]] == ["2024-05-01", "2024-06-01"]


async def test_written_archive_holds_the_seed_and_its_files(tmp_path: Path) -> None:
    directory = tmp_path / "smoke"
    (directory / "stale").mkdir(parents=True)
    await write_smoke_archive(directory)
    assert sorted(p.name for p in directory.iterdir()) == ["archive.db", "attachments"]
    assert len(list((directory / "attachments").rglob("*.*"))) == 10


async def test_the_media_screen_has_a_gif_a_video_and_images_of_several_shapes(
    client: AsyncClient,
) -> None:
    """The Media screen's smoke tests filter by type and check badges and tile shapes (#62)."""
    timeline = f"/api/guilds/{GUILD_ID}/gallery/timeline"

    async def attachments(content_type: str) -> list[dict[str, object]]:
        payload = (await client.get(timeline, params={"content_type": content_type})).json()
        return [a for g in payload["groups"] for a in g["attachments"]]

    media = await attachments("media")
    assert len(media) == 8
    assert {str(a["created_at"])[:7] for a in media} == {"2024-05", "2024-06"}
    sizes = {a["filename"]: (a["width"], a["height"]) for a in media}
    assert sizes["unmeasured.png"] == (None, None)
    assert sizes["tall-poster.png"] == (3, 4)

    magic = {"video": b"\x1a\x45\xdf\xa3", "gif": b"GIF89a"}
    for content_type, filename in [("video", "clip.webm"), ("gif", "wumpus-dance.gif")]:
        [found] = await attachments(content_type)
        assert found["filename"] == filename
        url = str(found["url"])
        assert url.startswith("/attachments/")
        assert (await client.get(url)).content.startswith(magic[content_type])


async def test_search_finds_the_links_and_the_markup(client: AsyncClient) -> None:
    """#64's smoke tests filter by has:link and from:zara, and highlight escaped markup."""

    async def search(**params: object) -> Any:
        response = await client.get("/api/search", params={"guild_id": GUILD_ID, **params})
        return response.json()

    zara = SORTED_APART[0][0]
    assert (await search(has="link"))["total"] == 2
    assert (await search(has="link", author_id=zara))["total"] == 1
    assert (await search(author_id=zara))["total"] == 3
    assert (await search(has="image"))["total"] == 5
    echo = await search(q="echo")
    assert echo["results"][0]["highlight"] == (
        "Lurker 102 shouts <mark>echo</mark> &lt;b&gt;<mark>echo</mark>&lt;/b&gt; &amp; "
        "<mark>echo</mark>!"
    )


# ── #63 Browse's Pinned tab ──────────────────────────────────────────────────


async def test_general_has_two_pinned_messages_and_random_one(client: AsyncClient) -> None:
    """Browse's Pinned tab smoke test lists #general's two and not #random's."""
    assert len(PINNED) == 3

    async def pinned(channel_id: int) -> tuple[list[str], int]:
        url = f"/api/channels/{channel_id}/messages"
        page = (await client.get(url, params={"pinned": "true"})).json()
        return [m["content"] for m in page["messages"]], page["total"]

    general = ["The hello world of June.", "Anyone up for a game tonight?"]
    assert await pinned(GENERAL_ID) == (general, 2)
    assert await pinned(RANDOM_ID) == (["Agreed."], 1)
    assert await pinned(ART_ID) == ([], 0)


# ── #61 Browse's grouped feed ────────────────────────────────────────────────


async def test_lobby_has_an_author_two_minutes_apart_and_one_ten_minutes_apart(
    client: AsyncClient,
) -> None:
    """Browse's smoke tests see Zara's messages as one group and aaron's as two."""
    page = await client.get(f"/api/channels/{LOBBY_ID}/messages", params={"limit": 5})
    times: dict[str, list[datetime]] = {}
    for message in reversed(page.json()["messages"]):
        name = message["author"]["display_name"]
        times.setdefault(name, []).append(datetime.fromisoformat(message["created_at"]))
    gaps = {name: [b - a for a, b in itertools.pairwise(at)] for name, at in times.items()}
    assert gaps == {"Zara": [timedelta(minutes=2)] * 2, "aaron": [timedelta(minutes=10)]}


async def test_a_reply_in_general_names_the_message_it_answers(client: AsyncClient) -> None:
    """Browse's smoke tests follow "Thanks, glad to be here." to Alice's welcome."""
    messages = (await client.get(f"/api/channels/{GENERAL_ID}/messages")).json()["messages"]
    thanks = next(m for m in messages if m["content"] == "Thanks, glad to be here.")
    reference = thanks["reference"]
    assert (reference["author"]["display_name"], reference["snippet"]) == (
        "Alice",
        "Welcome to the smoke test guild!",
    )
