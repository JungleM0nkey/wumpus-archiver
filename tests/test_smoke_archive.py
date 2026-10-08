"""The smoke archive holds what the portal smoke suite looks for.

The portal suite only sees the archive through a browser; these tests pin the seed
itself through the API, so a change to it fails here first and says why.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.smoke_archive import (
    ALICE_ID,
    ART_ID,
    GUILD_ID,
    LURKERS,
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
    assert totals == (12 + LURKERS, 2 + LURKERS, 4)


async def test_the_people_screen_has_a_third_page(client: AsyncClient) -> None:
    """The People screen pages 50 authors at a time; its smoke test clicks Load more twice."""
    params = {"offset": 100, "limit": 50}
    page = (await client.get(f"/api/guilds/{GUILD_ID}/users", params=params)).json()
    assert (len(page["users"]), page["total"], page["has_more"]) == (20, 120, False)


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


async def test_search_and_profile_find_the_seeded_text(client: AsyncClient) -> None:
    search = (await client.get("/api/search", params={"q": "hello"})).json()
    assert [r["message"]["content"] for r in search["results"]] == ["The hello world of June."]
    profile = (await client.get(f"/api/users/{ALICE_ID}/profile")).json()
    assert profile["display_name"] == "Alice"


async def test_written_archive_holds_the_seed_and_its_files(tmp_path: Path) -> None:
    directory = tmp_path / "smoke"
    (directory / "stale").mkdir(parents=True)
    await write_smoke_archive(directory)
    assert sorted(p.name for p in directory.iterdir()) == ["archive.db", "attachments"]
    assert len(list((directory / "attachments").rglob("*.*"))) == 4
