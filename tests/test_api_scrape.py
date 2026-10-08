"""The scrape routes over a fake scrape control: a job's live progress, cancel and history.

This is what the Archive screen reads: the status while a job runs (with each channel
it has reached), the job's end on cancel, and the history that then lists it.
"""

import pytest
from httpx import AsyncClient

from tests.fakes import FakeScrapeControl
from wumpus_archiver.api.scrape_control import ScrapeControl

# An obvious fake, never a real credential
API_TOKEN = "test-api-token-not-a-real-secret"
AUTH = {"Authorization": f"Bearer {API_TOKEN}"}


@pytest.fixture
def fake() -> FakeScrapeControl:
    return FakeScrapeControl()


@pytest.fixture
def scrape(fake: FakeScrapeControl) -> ScrapeControl:
    return fake


@pytest.fixture
def api_auth_token() -> str:
    return API_TOKEN


async def test_a_job_reports_each_channel_it_reaches(
    client: AsyncClient, fake: FakeScrapeControl
) -> None:
    started = await client.post("/api/scrape/start", json={"guild_id": 42}, headers=AUTH)
    assert started.status_code == 202
    assert started.json()["job"]["progress"]["channels"] == []

    fake.report("general", 100)
    fake.report("general", 140)
    fake.report("art", 7)

    status = (await client.get("/api/scrape/status")).json()
    assert status["busy"] is True
    progress = status["current_job"]["progress"]
    assert progress["channels"] == [
        {"name": "general", "messages": 140, "done": True},
        {"name": "art", "messages": 7, "done": False},
    ]
    assert progress["current_channel"] == "art"
    assert progress["channels_done"] == 1
    assert progress["messages_scraped"] == 147


async def test_cancel_ends_the_job_and_history_lists_it(
    client: AsyncClient, fake: FakeScrapeControl
) -> None:
    await client.post("/api/scrape/start", json={"guild_id": 42}, headers=AUTH)
    fake.report("general", 12)
    assert (await client.get("/api/scrape/history")).json() == {"jobs": []}

    cancelled = await client.post("/api/scrape/cancel", headers=AUTH)
    assert cancelled.status_code == 200

    status = (await client.get("/api/scrape/status")).json()
    assert status["busy"] is False
    assert status["current_job"]["status"] == "cancelled"
    jobs = (await client.get("/api/scrape/history")).json()["jobs"]
    assert [(j["id"], j["status"], j["guild_id"]) for j in jobs] == [("job1", "cancelled", 42)]
    assert jobs[0]["progress"]["channels"] == [{"name": "general", "messages": 12, "done": False}]


async def test_a_finished_job_has_every_channel_done(
    client: AsyncClient, fake: FakeScrapeControl
) -> None:
    await client.post("/api/scrape/start", json={"guild_id": 42}, headers=AUTH)
    fake.report("general", 12)
    fake.report("art", 3)
    fake.finish(channels_scraped=2)

    jobs = (await client.get("/api/scrape/history")).json()["jobs"]
    assert [c["done"] for c in jobs[0]["progress"]["channels"]] == [True, True]
