"""Replay an archived Discord guild into apehost chat via the bridge.

Reads the wumpus-archiver SQLite archive and re-sends every non-bot message
(attachments included) through the same bridge the live mirror uses, preserving
original timestamps. Cut off at a datetime (typically the live mirror's start)
so live-forwarded messages are not duplicated.
"""

import asyncio
import logging
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wumpus_archiver.bot.mirror import (
    MAX_CONTENT,
    BridgeClient,
    mirror_channel_name,
    sender_slug,
)

logger = logging.getLogger(__name__)

# discord.ChannelType.text / voice; excludes threads (11/12), forums, categories
MIRRORED_CHANNEL_TYPES = (0, 2)


def _created_ms(naive_utc: str) -> int:
    dt = datetime.fromisoformat(naive_utc).replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def row_payload(
    row: sqlite3.Row,
    attachments: list[sqlite3.Row],
) -> dict[str, Any] | None:
    """Build a bridge send body from an archive row, or None if not mirrorable."""
    if row["bot"]:
        return None
    content = (row["clean_content"] or row["content"] or "").strip()
    media: dict[str, Any] | None = None
    extra: list[str] = []
    for att in attachments:
        if media is None and (att["content_type"] or "").startswith("image/"):
            media = {
                "url": att["url"],
                "thumbnail_url": att["url"],
                "type": "image",
                "width": att["width"],
                "height": att["height"],
                "alt": (att["filename"] or "")[:256],
            }
        else:
            extra.append(att["url"])
    if extra:
        content = f"{content}\n{'\n'.join(extra)}".strip()
    if not content and not media:
        return None
    if len(content) > MAX_CONTENT:
        content = content[: MAX_CONTENT - 1] + "…"
    return {
        "sender": sender_slug(row["name"], row["global_name"]),
        "content": content,
        "media": media,
        "created_at": _created_ms(row["created_at"]),
    }


def _channel_batches(
    db: sqlite3.Connection,
    guild_id: int,
    cutoff: datetime,
    batch: int = 500,
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Yield (channel_name, payloads) batches, messages in chronological order."""
    cutoff_iso = cutoff.replace(tzinfo=None).isoformat(sep=" ")
    db.row_factory = sqlite3.Row
    channels = db.execute(
        "SELECT id, name FROM channels WHERE guild_id = ? AND type IN (?, ?)",
        (guild_id, *MIRRORED_CHANNEL_TYPES),
    ).fetchall()
    for chan in channels:
        msgs = db.execute(
            """SELECT m.id, m.content, m.clean_content, m.created_at,
                      u.username AS name, u.global_name, COALESCE(u.bot, 0) AS bot
               FROM messages m LEFT JOIN users u ON m.author_id = u.id
               WHERE m.channel_id = ? AND m.created_at < ?
               ORDER BY m.created_at ASC, m.id ASC""",
            (chan["id"], cutoff_iso),
        ).fetchall()
        payloads = []
        if msgs:
            ids = [m["id"] for m in msgs]
            atts: dict[int, list[sqlite3.Row]] = {}
            placeholders = ",".join("?" * len(ids))
            for att in db.execute(
                "SELECT message_id, filename, content_type, url, width, height"
                f" FROM attachments WHERE message_id IN ({placeholders})",
                ids,
            ):
                atts.setdefault(att["message_id"], []).append(att)
            for m in msgs:
                p = row_payload(m, atts.get(m["id"], []))
                if p:
                    payloads.append(p)
        for i in range(0, len(payloads), batch):
            yield chan["name"], payloads[i : i + batch]


def _user_entries(db: sqlite3.Connection, guild_id: int) -> list[dict[str, str]]:
    """Directory entries for every non-bot author seen in the guild's channels."""
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """SELECT DISTINCT u.id, u.username, u.global_name, u.avatar_url
           FROM users u
           JOIN messages m ON m.author_id = u.id
           JOIN channels c ON m.channel_id = c.id
           WHERE c.guild_id = ? AND COALESCE(u.bot, 0) = 0""",
        (guild_id,),
    ).fetchall()
    entries: list[dict[str, str]] = []
    for u in rows:
        display = (u["global_name"] or u["username"] or "user").strip()
        if not display:
            continue
        entries.append(
            {
                # ponytail: slug collisions between same-named users share one entry (last wins)
                "slug": sender_slug(u["username"], u["global_name"]),
                "display_name": display[:64],
                "avatar_url": u["avatar_url"] or "",
            }
        )
    return entries


async def _push_users(bridge: BridgeClient, entries: list[dict[str, str]]) -> None:
    for i in range(0, len(entries), 500):
        await bridge.put_users(entries[i : i + 500])


async def run_backfill(
    db_path: Path,
    guild_id: int,
    bridge: BridgeClient,
    cutoff: datetime,
    concurrency: int = 8,
    skip_messages: bool = False,
) -> int:
    """Replay the archive into chat. Returns the number of messages sent."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    sem = asyncio.Semaphore(max(1, concurrency))
    sent = 0
    failed = 0

    async def send_one(payload: dict[str, Any], room: str) -> bool:
        nonlocal sent, failed
        async with sem:
            ok = await bridge.post("send", {**payload, "room_id": room}) is not None
        if ok:
            sent += 1
        else:
            failed += 1
        return ok

    try:
        entries = _user_entries(db, guild_id)
        await _push_users(bridge, entries)
        print(f"Pushed {len(entries)} user directory entries", flush=True)
        if not skip_messages:
            for chan_name, payloads in _channel_batches(db, guild_id, cutoff):
                chat_name = mirror_channel_name(chan_name)
                room_id = await bridge.room_for(chat_name, f"Mirror of Discord #{chan_name}")
                if room_id is None:
                    logger.warning("could not resolve room for %s; skipping %d messages", chat_name, len(payloads))
                    failed += len(payloads)
                    continue
                await asyncio.gather(*(send_one(p, room_id) for p in payloads))
                print(f"  #{chan_name}: {len(payloads)} messages -> {chat_name}", flush=True)
    finally:
        db.close()
    print(f"Backfill done: sent={sent} failed={failed}", flush=True)
    return sent
