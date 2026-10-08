"""The small archive the portal smoke suite browses, and the command that writes it.

Two guilds. The first, "Smoke Test Guild", has two categories, four text channels, a
voice channel that Browse leaves out (#60), two regular authors and a dozen messages
spread over two months, including a reply, reactions, three pinned messages (#63)
and local attachments (three images and a text file on #art; on #random a GIF, a
video and images of other shapes for the Media screen). Beside them, enough
one-message authors ("lurkers", all in #lobby) that the People screen fills three
pages, and two more in #lobby whose order by name is not their order by messages
(#65). The second, "Night Owls", is smaller and shares nothing with the first: its own
category, two channels, two authors, five messages and one local image, so the suite
can tell which guild a screen shows. Three #lobby messages carry links and markup for
Search (#64). Ids are Discord-sized snowflakes, past
JavaScript's safe integer range, so the portal is exercised with ids it must keep as
strings.

``python -m tests.smoke_archive <dir>`` writes ``<dir>/archive.db`` and the local
attachments under ``<dir>/attachments``, replacing whatever was there. The smoke
suite then serves that directory with ``wumpus-archiver serve``. Python tests seed a
connected ``Database`` with ``seed_smoke_archive`` instead.
"""

import asyncio
import shutil
import struct
import sys
import zlib
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.completed_scrape import CompletedScrape
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database

GUILD_ID = 900000000000000001
TEXT_CATEGORY_ID = 900000000000000010
MEDIA_CATEGORY_ID = 900000000000000011
GENERAL_ID = 900000000000000020
RANDOM_ID = 900000000000000021
ART_ID = 900000000000000022
LOBBY_ID = 900000000000000023
ALICE_ID = 900000000000000100
BOB_ID = 900000000000000101

NIGHT_GUILD_ID = 900000000000000002
NIGHT_CATEGORY_ID = 900000000000000030
LOUNGE_ID = 900000000000000031
PHOTOS_ID = 900000000000000032
CAROL_ID = 900000000000000110
DAVE_ID = 900000000000000111

GUILD_TEXT = 0
GUILD_VOICE = 2
GUILD_CATEGORY = 4

# #60 (Browse): a voice channel under "Text Channels", which the channel pane leaves out.
HANGOUT_ID = 900000000000000024

START = datetime(2024, 5, 20, 12, 0)
"""The first message's time; later messages follow at increasing offsets."""

# (channel, author, minutes after START, content). Message ids follow this order.
_MESSAGES: list[tuple[int, int, int, str]] = [
    (GENERAL_ID, ALICE_ID, 0, "Welcome to the smoke test guild!"),
    (GENERAL_ID, BOB_ID, 5, "Thanks, glad to be here."),
    (GENERAL_ID, ALICE_ID, 60, "Anyone up for a game tonight?"),
    (GENERAL_ID, BOB_ID, 65, "Count me in."),
    (RANDOM_ID, BOB_ID, 2 * 24 * 60, "Random thought: wumpus is the best mascot."),
    (RANDOM_ID, ALICE_ID, 2 * 24 * 60 + 3, "Agreed."),
    (ART_ID, ALICE_ID, 10 * 24 * 60, "My first sketch"),
    (ART_ID, BOB_ID, 10 * 24 * 60 + 30, "Here is mine, plus the notes"),
    (GENERAL_ID, ALICE_ID, 20 * 24 * 60, "June already?"),
    (GENERAL_ID, BOB_ID, 32 * 24 * 60, "The hello world of June."),
    (ART_ID, ALICE_ID, 33 * 24 * 60, "Another drawing"),
    (RANDOM_ID, BOB_ID, 40 * 24 * 60, "Last message in the archive."),
]
_FIRST_MESSAGE_ID = 900000000000001000

_REPLIES = {1: 0, 3: 2, 7: 6}
"""Message index -> index of the message it replies to."""

# ── #63 Browse's Pinned tab ──────────────────────────────────────────────────
# Two pinned messages in #general ("Anyone up for a game tonight?" and "The hello world
# of June.") and one in #random ("Agreed."), so #general's Pinned tab must list its own
# two and not the third. Message indexes into _MESSAGES, as _REPLIES.
PINNED = {2, 9, 5}

_REACTIONS: dict[int, list[tuple[str, int]]] = {
    0: [("👋", 2), ("🎉", 1)],
    6: [("🔥", 2)],
    10: [("❤️", 1)],
}
"""Message index -> (emoji, count) reactions."""

_AttachmentRow = tuple[int, str, str, int | None, int | None]
"""(message index, filename, content type, width, height or None when not recorded)."""

_ATTACHMENTS: list[_AttachmentRow] = [
    (6, "sketch.png", "image/png", 4, 3),
    (7, "drawing.png", "image/png", 4, 3),
    (7, "notes.txt", "text/plain", None, None),
    (10, "another.png", "image/png", 4, 3),
]
_FIRST_ATTACHMENT_ID = 900000000000002000

LURKERS = 118
"""Authors with one message each: with Alice and Bob, two full People pages of 50 and 20 more."""
_FIRST_LURKER_ID = 900000000000000200
_FIRST_LURKER_MESSAGE_ID = 900000000000003000
_LURKERS_FROM = 21 * 24 * 60
"""Minutes after START of the first lurker's message, between the regular messages."""

# ── #65 People and Profile ────────────────────────────────────────────────────
# Two authors in #lobby whose order by name differs from their order by messages, so
# sorting the People table reorders it: Zara posts three messages and sorts last by
# name; "aaron", a lowercase global name, posts two and sorts first, ignoring case.
SORTED_APART: list[tuple[int, str, str, int]] = [
    (900000000000000120, "zara", "Zara", 3),
    (900000000000000121, "aaron.k", "aaron", 2),
]
"""(user id, username, global name, messages)."""
SORTED_APART_MESSAGES = sum(messages for *_, messages in SORTED_APART)
_FIRST_SORTED_APART_MESSAGE_ID = 900000000000006500
_SORTED_APART_FROM = 22 * 24 * 60
"""Minutes after START of their first message, a day after the lurkers'."""


NIGHT_START = datetime(2024, 7, 1, 21, 0)
"""The second guild's first message's time."""

# The second guild's messages, as _MESSAGES. "game" is also in the first guild's
# general, so a search for it tells the guilds apart.
_NIGHT_MESSAGES: list[tuple[int, int, int, str]] = [
    (LOUNGE_ID, CAROL_ID, 0, "Game night is on Friday."),
    (LOUNGE_ID, DAVE_ID, 4, "I will bring the snacks."),
    (PHOTOS_ID, CAROL_ID, 3 * 24 * 60, "Moonrise over the harbour"),
    (LOUNGE_ID, CAROL_ID, 5 * 24 * 60, "Night owls unite."),
    (PHOTOS_ID, DAVE_ID, 9 * 24 * 60, "Long exposure attempt"),
]
_FIRST_NIGHT_MESSAGE_ID = 900000000000004000

# As _ATTACHMENTS, indexing _NIGHT_MESSAGES.
_NIGHT_ATTACHMENTS: list[_AttachmentRow] = [
    (2, "moonrise.png", "image/png", 4, 3),
]
_FIRST_NIGHT_ATTACHMENT_ID = 900000000000002100

# ── The Media screen (#62) ──────────────────────────────────────────────────
# Media on Bob's two messages in #random, so the Media screen has a GIF, a video and
# images of several shapes to lay out, badge and filter by type, over two months. They
# stay off #art and Alice, whose attachments other smoke tests count. One image has
# no recorded size,
# as Discord sometimes leaves it, so the screen's fallback is exercised. As
# _ATTACHMENTS, indexing _MESSAGES.
_MEDIA_ATTACHMENTS: list[_AttachmentRow] = [
    (4, "wumpus-dance.gif", "image/gif", 160, 160),
    (4, "tall-poster.png", "image/png", 3, 4),
    (4, "unmeasured.png", "image/png", None, None),
    (11, "clip.webm", "video/webm", 320, 180),
    (11, "panorama.png", "image/png", 21, 9),
]
_FIRST_MEDIA_ATTACHMENT_ID = 900000000000002200
_MEDIA_DIR = Path(__file__).parent / "smoke_media"
"""Real GIF and WebM files, too fiddly to generate here: a 2-frame 160x160 GIF and a
1-second 320x180 VP8 WebM (VP8, since Chromium builds without H.264 decode it)."""


def _media_file(filename: str) -> bytes:
    """The content of one of the Media screen's attachments."""
    if filename == "tall-poster.png":
        return _png(3, 4, (87, 242, 135))
    if filename == "unmeasured.png":
        return _png(2, 1, (254, 231, 92))
    if filename == "panorama.png":
        return _png(21, 9, (237, 66, 69))
    return (_MEDIA_DIR / filename).read_bytes()


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A valid solid-colour PNG, so the browser decodes it without an error."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes(rgb) * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


def _attachment_rows() -> list[tuple[int, int, int, _AttachmentRow]]:
    """Every attachment as (attachment id, message id, channel id, its row)."""
    return [
        (first_attachment + offset, first_message + row[0], messages[row[0]][0], row)
        for first_attachment, first_message, messages, rows in (
            (_FIRST_ATTACHMENT_ID, _FIRST_MESSAGE_ID, _MESSAGES, _ATTACHMENTS),
            (
                _FIRST_NIGHT_ATTACHMENT_ID,
                _FIRST_NIGHT_MESSAGE_ID,
                _NIGHT_MESSAGES,
                _NIGHT_ATTACHMENTS,
            ),
            (_FIRST_MEDIA_ATTACHMENT_ID, _FIRST_MESSAGE_ID, _MESSAGES, _MEDIA_ATTACHMENTS),
        )
        for offset, row in enumerate(rows)
    ]


def attachment_files() -> dict[str, bytes]:
    """The local attachments' contents by path relative to the attachments dir."""
    files: dict[str, bytes] = {}
    for offset, (attachment_id, _, _, row) in enumerate(_attachment_rows()):
        _, filename, content_type, width, height = row
        if attachment_id >= _FIRST_MEDIA_ATTACHMENT_ID:
            content = _media_file(filename)
        elif width is not None and height is not None:
            content = _png(width, height, (88, 101, 242 - 40 * offset))
        else:
            content = f"{content_type} attachment {filename}\n".encode()
        files[f"{attachment_id}/{filename}"] = content
    return files


async def seed_smoke_archive(database: Database) -> None:
    """Write the smoke archive's rows into a connected ``database`` that holds the schema."""
    last = START + timedelta(minutes=_MESSAGES[-1][2])
    counts = Counter(channel_id for channel_id, *_ in _MESSAGES)
    counts[LOBBY_ID] = LURKERS + SORTED_APART_MESSAGES

    async with database.session() as session:
        session.add(
            Guild(
                id=GUILD_ID,
                name="Smoke Test Guild",
                member_count=2,
                first_scraped_at=last,
                last_scraped_at=last,
                scrape_count=1,
            )
        )
        session.add_all(
            [
                Channel(
                    id=TEXT_CATEGORY_ID,
                    guild_id=GUILD_ID,
                    name="Text Channels",
                    type=GUILD_CATEGORY,
                    position=0,
                ),
                Channel(
                    id=MEDIA_CATEGORY_ID,
                    guild_id=GUILD_ID,
                    name="Media",
                    type=GUILD_CATEGORY,
                    position=1,
                ),
                Channel(
                    id=GENERAL_ID,
                    guild_id=GUILD_ID,
                    name="general",
                    type=GUILD_TEXT,
                    topic="Talk about anything",
                    position=0,
                    parent_id=TEXT_CATEGORY_ID,
                    message_count=counts[GENERAL_ID],
                    last_scraped_at=last,
                ),
                Channel(
                    id=RANDOM_ID,
                    guild_id=GUILD_ID,
                    name="random",
                    type=GUILD_TEXT,
                    position=1,
                    parent_id=TEXT_CATEGORY_ID,
                    message_count=counts[RANDOM_ID],
                    last_scraped_at=last,
                ),
                Channel(
                    id=ART_ID,
                    guild_id=GUILD_ID,
                    name="art",
                    type=GUILD_TEXT,
                    topic="Show your drawings",
                    position=0,
                    parent_id=MEDIA_CATEGORY_ID,
                    message_count=counts[ART_ID],
                    last_scraped_at=last,
                ),
                Channel(
                    id=LOBBY_ID,
                    guild_id=GUILD_ID,
                    name="lobby",
                    type=GUILD_TEXT,
                    topic="Say hi",
                    position=2,
                    parent_id=TEXT_CATEGORY_ID,
                    message_count=counts[LOBBY_ID],
                    last_scraped_at=last,
                ),
                # #60 (Browse): a voice channel, absent from Browse's channel pane.
                Channel(
                    id=HANGOUT_ID,
                    guild_id=GUILD_ID,
                    name="hangout",
                    type=GUILD_VOICE,
                    position=3,
                    parent_id=TEXT_CATEGORY_ID,
                    last_scraped_at=last,
                ),
                User(id=ALICE_ID, username="alice", global_name="Alice"),
                User(id=BOB_ID, username="bob", global_name="Bob"),
            ]
        )
        for index, (channel_id, author_id, minutes, content) in enumerate(_MESSAGES):
            reply_to = _REPLIES.get(index)
            session.add(
                Message(
                    id=_FIRST_MESSAGE_ID + index,
                    channel_id=channel_id,
                    author_id=author_id,
                    content=content,
                    clean_content=content,
                    created_at=START + timedelta(minutes=minutes),
                    reference_id=None if reply_to is None else _FIRST_MESSAGE_ID + reply_to,
                    pinned=index in PINNED,  # #63
                    scraped_at=last,
                )
            )
        _add_night_guild(session)
        _add_night_scrape(session)  # #67
        for n in range(LURKERS):
            name = f"Lurker {n + 1:03d}"
            session.add(
                User(id=_FIRST_LURKER_ID + n, username=f"lurker{n + 1:03d}", global_name=name)
            )
            session.add(
                Message(
                    id=_FIRST_LURKER_MESSAGE_ID + n,
                    channel_id=LOBBY_ID,
                    author_id=_FIRST_LURKER_ID + n,
                    content=_searched(_FIRST_LURKER_MESSAGE_ID + n, f"{name} says hi."),
                    clean_content=_searched(_FIRST_LURKER_MESSAGE_ID + n, f"{name} says hi."),
                    created_at=START + timedelta(minutes=_LURKERS_FROM + n),
                    scraped_at=last,
                )
            )
        _add_sorted_apart(session, scraped_at=last)
        for index, reactions in _REACTIONS.items():
            for emoji, count in reactions:
                session.add(
                    Reaction(message_id=_FIRST_MESSAGE_ID + index, emoji_name=emoji, count=count)
                )
        files = attachment_files()
        for attachment_id, message_id, channel_id, row in _attachment_rows():
            _, filename, content_type, width, height = row
            local_path = f"{attachment_id}/{filename}"
            session.add(
                Attachment(
                    id=attachment_id,
                    message_id=message_id,
                    filename=filename,
                    content_type=content_type,
                    size=len(files[local_path]),
                    url=f"https://cdn.discordapp.com/attachments/{channel_id}/{attachment_id}/{filename}",
                    width=width,
                    height=height,
                    local_path=local_path,
                    download_status="downloaded",
                )
            )


# ── #61 Browse's grouped feed ────────────────────────────────────────────────
# The feed groups one author's consecutive messages under one header while they follow
# it within 5 minutes. Zara's three messages are 2 minutes apart, so they read as one
# group; aaron's two are 10 minutes apart, so each has its own header. Each author's
# first message follows the previous author's last by a minute.
GROUPING_GAP_MINUTES = {SORTED_APART[0][0]: 2, SORTED_APART[1][0]: 10}
"""User id -> minutes between that author's consecutive messages in #lobby."""


def _add_sorted_apart(session: AsyncSession, *, scraped_at: datetime) -> None:
    """Add the #65 authors whose order by name is not their order by messages."""
    message_id = _FIRST_SORTED_APART_MESSAGE_ID
    at = START + timedelta(minutes=_SORTED_APART_FROM)
    for user_id, username, global_name, messages in SORTED_APART:
        session.add(User(id=user_id, username=username, global_name=global_name))
        for n in range(messages):
            content = _searched(message_id, f"{global_name} checks in, {n + 1} of {messages}.")
            session.add(
                Message(
                    id=message_id,
                    channel_id=LOBBY_ID,
                    author_id=user_id,
                    content=content,
                    clean_content=content,
                    created_at=at,
                    scraped_at=scraped_at,
                )
            )
            message_id += 1
            last = n == messages - 1
            at += timedelta(minutes=1 if last else GROUPING_GAP_MINUTES[user_id])


def _add_night_guild(session: AsyncSession) -> None:
    """Add the second guild, its channels, authors and messages (not its attachment)."""
    last = NIGHT_START + timedelta(minutes=_NIGHT_MESSAGES[-1][2])
    counts = Counter(channel_id for channel_id, *_ in _NIGHT_MESSAGES)
    session.add(
        Guild(
            id=NIGHT_GUILD_ID,
            name="Night Owls",
            member_count=2,
            first_scraped_at=last,
            last_scraped_at=last,
            scrape_count=1,
        )
    )
    session.add_all(
        [
            Channel(
                id=NIGHT_CATEGORY_ID,
                guild_id=NIGHT_GUILD_ID,
                name="After Hours",
                type=GUILD_CATEGORY,
                position=0,
            ),
            Channel(
                id=LOUNGE_ID,
                guild_id=NIGHT_GUILD_ID,
                name="lounge",
                type=GUILD_TEXT,
                topic="Late conversations",
                position=0,
                parent_id=NIGHT_CATEGORY_ID,
                message_count=counts[LOUNGE_ID],
                last_scraped_at=last,
            ),
            Channel(
                id=PHOTOS_ID,
                guild_id=NIGHT_GUILD_ID,
                name="photos",
                type=GUILD_TEXT,
                topic="Night shots",
                position=1,
                parent_id=NIGHT_CATEGORY_ID,
                message_count=counts[PHOTOS_ID],
                last_scraped_at=last,
            ),
            User(id=CAROL_ID, username="carol", global_name="Carol"),
            User(id=DAVE_ID, username="dave", global_name="Dave"),
        ]
    )
    for index, (channel_id, author_id, minutes, content) in enumerate(_NIGHT_MESSAGES):
        session.add(
            Message(
                id=_FIRST_NIGHT_MESSAGE_ID + index,
                channel_id=channel_id,
                author_id=author_id,
                content=_searched(_FIRST_NIGHT_MESSAGE_ID + index, content),
                clean_content=_searched(_FIRST_NIGHT_MESSAGE_ID + index, content),
                created_at=NIGHT_START + timedelta(minutes=minutes),
                scraped_at=last,
            )
        )


# ── #67 Overview: the change since the last completed scrape job ────────────
# Night Owls has one completed scrape job on record; Smoke Test Guild has none, so its
# stat tiles show no change at all. The job started when the guild held its first two
# messages (both in #lounge, by Carol and Dave) and no attachment, so it added three
# messages and moonrise.png: no channel and no author.
NIGHT_SCRAPE_ADDED = {"messages": 3, "channels": 0, "authors": 0, "attachments": 1}
"""What Night Owls' last completed scrape job added, as the stats report it."""


def _add_night_scrape(session: AsyncSession) -> None:
    """Record Night Owls' completed scrape job, with the totals it started from."""
    completed = NIGHT_START + timedelta(minutes=_NIGHT_MESSAGES[-1][2])
    session.add(
        CompletedScrape(
            guild_id=NIGHT_GUILD_ID,
            started_at=completed - timedelta(minutes=4),
            completed_at=completed,
            messages_at_start=2,
            channels_at_start=3,
            authors_at_start=2,
            attachments_at_start=0,
        )
    )


# ── #64 Search ──────────────────────────────────────────────────────────────
# Three #lobby messages say more than their seed text, with no row, id or count changed:
# Zara's second check-in and Lurker 101's greeting carry links, so `has:link` finds two
# messages and `from:zara has:link` one; Lurker 102 repeats "echo" around markup, so a
# highlight marks every occurrence and shows the markup as text.
ZARA_LINK_ID = _FIRST_SORTED_APART_MESSAGE_ID + 1
LURKER_LINK_ID = _FIRST_LURKER_MESSAGE_ID + 100
ECHO_ID = _FIRST_LURKER_MESSAGE_ID + 101
_SEARCH_CONTENT = {
    ZARA_LINK_ID: "Zara checks in, 2 of 3: https://example.com/zara",
    LURKER_LINK_ID: "Lurker 101 says hi, notes at https://example.com/lurk",
    ECHO_ID: "Lurker 102 shouts echo <b>echo</b> & echo!",
}

# ── #71 Switching guild on Search ───────────────────────────────────────────
# Night Owls' game night carries a link, so `game has:link` finds it once Search's
# guild-bound chips are dropped on a switch. No row, id or count changes.
NIGHT_GAME_ID = _FIRST_NIGHT_MESSAGE_ID
NIGHT_GAME = "Game night is on Friday. Sign up at https://example.com/game-night"
_SEARCH_CONTENT[NIGHT_GAME_ID] = NIGHT_GAME


def _searched(message_id: int, content: str) -> str:
    """A message's content: its seed text, or what #64's search tests need it to say."""
    return _SEARCH_CONTENT.get(message_id, content)


def write_attachments(attachments_dir: Path) -> None:
    """Write the local attachments' files under ``attachments_dir``."""
    for relative, content in attachment_files().items():
        path = attachments_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


async def write_smoke_archive(directory: Path) -> None:
    """Replace ``directory`` with ``archive.db`` and ``attachments/`` holding the smoke archive."""
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    database = Database(f"sqlite+aiosqlite:///{directory / 'archive.db'}")
    await database.connect()
    try:
        await database.create_tables()
        await seed_smoke_archive(database)
    finally:
        await database.disconnect()
    write_attachments(directory / "attachments")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m tests.smoke_archive <dir>")
    asyncio.run(write_smoke_archive(Path(sys.argv[1])))
