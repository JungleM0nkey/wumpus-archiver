"""A channel's message count after scrapes of a fake guild (no gateway, no network).

``Channel.message_count`` must equal the messages the archive holds for the channel
after any number of scrapes (#69).
"""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update

from tests.fakes import FakeDiscordGuild, fake_archiver_bot
from wumpus_archiver.api.scrape_control import JobStatus
from wumpus_archiver.api.scrape_manager import ScrapeJobManager
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.completed_scrape import CompletedScrape
from wumpus_archiver.models.message import Message
from wumpus_archiver.storage.database import Database

GUILD = 500
GENERAL = 510
RANDOM = 511


def _guild() -> FakeDiscordGuild:
    guild = FakeDiscordGuild(GUILD)
    guild.add_channel(GENERAL, "general", *range(1_000, 1_005))
    guild.add_channel(RANDOM, "random", 2_000, 2_001)
    return guild


async def _counts(database: Database) -> dict[int, tuple[int, int]]:
    """Each channel's (``message_count``, archived message rows)."""
    async with database.session() as session:
        rows = await session.execute(
            select(Channel.id, Channel.message_count).where(Channel.guild_id == GUILD)
        )
        counters: dict[int, int] = dict(rows.all())
        per_channel = await session.execute(
            select(Message.channel_id, func.count()).group_by(Message.channel_id)
        )
        archived: dict[int, int] = dict(per_channel.all())
    return {channel: (count, archived.get(channel, 0)) for channel, count in counters.items()}


async def test_scraping_the_same_guild_twice_keeps_each_count_equal_to_its_messages(
    database: Database,
) -> None:
    bot = fake_archiver_bot(database, _guild())

    await bot.scrape_guild(GUILD)
    await bot.scrape_guild(GUILD)

    assert await _counts(database) == {GENERAL: (5, 5), RANDOM: (2, 2)}


async def test_a_rescrape_that_finds_new_messages_raises_the_count_by_exactly_those(
    database: Database,
) -> None:
    guild = _guild()
    bot = fake_archiver_bot(database, guild)
    await bot.scrape_guild(GUILD)

    guild.text_channels[0].post(1_005, 1_006, 1_007)
    await bot.scrape_guild(GUILD)

    assert await _counts(database) == {GENERAL: (8, 8), RANDOM: (2, 2)}


async def test_the_next_scrape_corrects_counts_an_earlier_scrape_inflated(
    database: Database,
) -> None:
    """The repair path for existing archives is the next scrape of the guild.

    It also corrects a channel whose history reads empty this time: its archived
    messages are still counted.
    """
    guild = _guild()
    bot = fake_archiver_bot(database, guild)
    await bot.scrape_guild(GUILD)
    async with database.session() as session:
        # What the scraper used to leave after a few re-scrapes.
        await session.execute(update(Channel).values(message_count=Channel.message_count * 3))
    assert await _counts(database) == {GENERAL: (15, 5), RANDOM: (6, 2)}

    guild.text_channels[1].message_ids.clear()
    await bot.scrape_guild(GUILD)

    assert await _counts(database) == {GENERAL: (5, 5), RANDOM: (2, 2)}


async def test_the_channels_and_stats_routes_count_each_channels_messages_after_a_rescrape(
    database: Database, client: AsyncClient
) -> None:
    bot = fake_archiver_bot(database, _guild())
    await bot.scrape_guild(GUILD)
    await bot.scrape_guild(GUILD)

    channels = (await client.get(f"/api/guilds/{GUILD}/channels")).json()["channels"]
    assert {c["name"]: c["message_count"] for c in channels} == {"general": 5, "random": 2}

    stats = (await client.get(f"/api/guilds/{GUILD}/stats")).json()
    assert stats["total_messages"] == 7
    assert {c["name"]: c["message_count"] for c in stats["top_channels"]} == {
        "general": 5,
        "random": 2,
    }


# A channel's first and last message ids after scrapes (#70): they name the oldest and
# newest messages the archive holds for the channel, whatever a given scrape read.


async def _message_ids(database: Database) -> dict[int, tuple[int | None, int | None]]:
    """Each channel's (``first_message_id``, ``last_message_id``)."""
    async with database.session() as session:
        rows = await session.execute(
            select(Channel.id, Channel.first_message_id, Channel.last_message_id).where(
                Channel.guild_id == GUILD
            )
        )
    return {channel: (first, last) for channel, first, last in rows.all()}


async def test_a_rescrape_that_reaches_older_messages_moves_the_first_message_id_back(
    database: Database,
) -> None:
    guild = _guild()
    bot = fake_archiver_bot(database, guild)
    await bot.scrape_guild(GUILD)
    assert (await _message_ids(database))[GENERAL] == (1_000, 1_004)

    # History the first scrape did not reach, older than anything it archived.
    guild.text_channels[0].post(900, 901)
    await bot.scrape_guild(GUILD)

    assert await _message_ids(database) == {GENERAL: (900, 1_004), RANDOM: (2_000, 2_001)}


async def test_a_channel_first_scraped_empty_gets_both_ids_once_it_has_messages(
    database: Database,
) -> None:
    guild = _guild()
    quiet = guild.add_channel(512, "quiet")
    bot = fake_archiver_bot(database, guild)
    await bot.scrape_guild(GUILD)
    assert (await _message_ids(database))[512] == (None, None)

    quiet.post(3_000, 3_001, 3_002)
    await bot.scrape_guild(GUILD)

    assert (await _message_ids(database))[512] == (3_000, 3_002)


async def test_a_rescrape_that_reads_less_keeps_the_ids_of_the_messages_still_archived(
    database: Database,
) -> None:
    """Messages a scrape no longer reads stay archived, so the ids still name them."""
    guild = _guild()
    bot = fake_archiver_bot(database, guild)
    await bot.scrape_guild(GUILD)

    guild.text_channels[0].message_ids[:] = [1_002]
    guild.text_channels[1].message_ids.clear()
    await bot.scrape_guild(GUILD)

    assert await _message_ids(database) == {GENERAL: (1_000, 1_004), RANDOM: (2_000, 2_001)}


async def test_a_rescrape_refreshes_a_channels_details_and_keeps_its_archive_metadata(
    database: Database,
) -> None:
    guild = _guild()
    general = guild.text_channels[0]
    bot = fake_archiver_bot(database, guild)
    await bot.scrape_guild(GUILD)

    general.name = "lobby"
    general.topic = "Say hello"
    general.position = 3
    general.category_id = 590
    general.type.value = 5  # converted to an announcement channel
    await bot.scrape_guild(GUILD)

    async with database.session() as session:
        stored = await session.get(Channel, GENERAL)
        assert stored is not None
        assert (stored.name, stored.topic, stored.position, stored.parent_id, stored.type) == (
            "lobby",
            "Say hello",
            3,
            590,
            5,
        )
        assert (stored.guild_id, stored.first_message_id, stored.last_message_id) == (
            GUILD,
            1_000,
            1_004,
        )
        assert stored.message_count == 5
        assert stored.last_scraped_at is not None


# A scrape job cancelled after the scraper starts leaves no completed scrape (ADR 0004),
# and stays cancelled; one that completes leaves exactly one.


async def _completed_scrapes(database: Database) -> int:
    async with database.session() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(CompletedScrape)
                .where(CompletedScrape.guild_id == GUILD)
            )
            or 0
        )


def _manager_on(
    monkeypatch: pytest.MonkeyPatch, database: Database, guild: FakeDiscordGuild
) -> ScrapeJobManager:
    """A scrape job manager whose jobs run the real scraper over ``guild``."""
    import wumpus_archiver.bot.scraper as scraper

    bot = fake_archiver_bot(database, guild)
    monkeypatch.setattr(scraper, "ArchiverBot", lambda _token, _database: bot)
    return ScrapeJobManager(database, "token")


async def _job_ends(manager: ScrapeJobManager) -> None:
    assert manager._task is not None
    await asyncio.wait_for(manager._task, timeout=5)


async def test_a_job_cancelled_mid_scrape_records_no_completed_scrape(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelled while the last archived thread is read: no request follows the close,
    so nothing in the scrape fails, yet the job did not complete."""
    guild = _guild()
    thread = guild.text_channels[1].archive_thread(520, "old-thread", 3_000, 3_001)
    thread.hold = asyncio.Event()
    manager = _manager_on(monkeypatch, database, guild)

    job = manager.start_scrape(GUILD)
    await asyncio.wait_for(thread.reached.wait(), timeout=5)
    assert manager.cancel() is True
    await asyncio.sleep(0)  # the cancel closes the bot's connection
    thread.hold.set()
    await _job_ends(manager)

    assert await _completed_scrapes(database) == 0
    assert job.status == JobStatus.CANCELLED
    assert [(j.id, j.status) for j in manager.history] == [(job.id, JobStatus.CANCELLED)]


async def test_a_job_that_completes_records_one_completed_scrape(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    guild = _guild()
    guild.text_channels[1].archive_thread(520, "old-thread", 3_000, 3_001)
    manager = _manager_on(monkeypatch, database, guild)

    job = manager.start_scrape(GUILD)
    await _job_ends(manager)

    assert job.status == JobStatus.COMPLETED
    assert job.result is not None and job.result["messages_scraped"] == 9
    assert await _completed_scrapes(database) == 1
