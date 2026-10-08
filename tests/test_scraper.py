"""A channel's message count after scrapes of a fake guild (no gateway, no network).

``Channel.message_count`` must equal the messages the archive holds for the channel
after any number of scrapes (#69).
"""

from httpx import AsyncClient
from sqlalchemy import func, select, update

from tests.fakes import FakeDiscordGuild, fake_archiver_bot
from wumpus_archiver.models.channel import Channel
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
