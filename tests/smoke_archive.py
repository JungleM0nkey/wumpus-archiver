"""The small archive the portal smoke suite browses, and the command that writes it.

Two guilds. The first, "Smoke Test Guild", has two categories, four text channels, two
regular authors and a dozen messages spread over two months, including a reply,
reactions and local attachments (two images and a text file). Beside them, enough
one-message authors ("lurkers", all in #lobby) that the People screen fills three
pages. The second, "Night Owls", is smaller and shares nothing with the first: its own
category, two channels, two authors, five messages and one local image, so the suite
can tell which guild a screen shows. Ids are Discord-sized snowflakes, past
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
GUILD_CATEGORY = 4

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

_REACTIONS: dict[int, list[tuple[str, int]]] = {
    0: [("👋", 2), ("🎉", 1)],
    6: [("🔥", 2)],
    10: [("❤️", 1)],
}
"""Message index -> (emoji, count) reactions."""

_AttachmentRow = tuple[int, str, str, int | None, int | None]
"""(message index, filename, content type, width, height or None for a non-image)."""

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
        )
        for offset, row in enumerate(rows)
    ]


def attachment_files() -> dict[str, bytes]:
    """The local attachments' contents by path relative to the attachments dir."""
    files: dict[str, bytes] = {}
    for offset, (attachment_id, _, _, row) in enumerate(_attachment_rows()):
        _, filename, content_type, width, height = row
        if width is not None and height is not None:
            content = _png(width, height, (88, 101, 242 - 40 * offset))
        else:
            content = f"{content_type} attachment {filename}\n".encode()
        files[f"{attachment_id}/{filename}"] = content
    return files


async def seed_smoke_archive(database: Database) -> None:
    """Write the smoke archive's rows into a connected ``database`` that holds the schema."""
    last = START + timedelta(minutes=_MESSAGES[-1][2])
    counts = Counter(channel_id for channel_id, *_ in _MESSAGES)
    counts[LOBBY_ID] = LURKERS

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
                    scraped_at=last,
                )
            )
        _add_night_guild(session)
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
                    content=f"{name} says hi.",
                    clean_content=f"{name} says hi.",
                    created_at=START + timedelta(minutes=_LURKERS_FROM + n),
                    scraped_at=last,
                )
            )
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
                content=content,
                clean_content=content,
                created_at=NIGHT_START + timedelta(minutes=minutes),
                scraped_at=last,
            )
        )


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
