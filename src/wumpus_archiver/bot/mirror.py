"""Live Discord -> apehost chat mirror bot.

Forwards messages from one Discord guild into apehost-connect chat channels via
the dashboard Worker's secret-authenticated bridge (``POST /dashboard/chat/bridge``).
Each Discord text/voice channel maps to one chat channel named ``discord-<name>``
(find-or-create, stateless); each Discord author becomes a ``discord-<slug>``
sender. v1 mirrors new messages only — edits, deletes, reactions, and threads
are not forwarded.
"""

import asyncio
import logging
import re
from datetime import UTC
from typing import Any

import aiohttp
import discord

logger = logging.getLogger(__name__)

BRIDGE_SENDER_PREFIX = "discord-"
MAX_CONTENT = 4000  # must match the chat Worker's cap
MAX_CHANNEL_NAME = 64  # must match the chat Worker's validChannelName

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def sender_slug(user: discord.abc.User) -> str:
    """Stable chat slug for a Discord author: ``discord-<sanitized name>``."""
    name = user.global_name or user.name or "user"
    slug = _SLUG_STRIP.sub("-", name.lower()).strip("-")[:32].strip("-")
    return f"{BRIDGE_SENDER_PREFIX}{slug or 'user'}"


def mirror_channel_name(channel_name: str) -> str:
    """Chat channel name for a Discord channel: ``discord-<name>``, capped."""
    return f"{BRIDGE_SENDER_PREFIX}{channel_name}".strip()[:MAX_CHANNEL_NAME]


def build_payload(message: discord.Message) -> dict[str, Any] | None:
    """Build a bridge send body from a Discord message, or None if not mirrorable.

    The first image attachment becomes the message media; every other attachment
    (any type) is appended to the content as a URL line.
    """
    content = message.clean_content.strip()
    media: dict[str, Any] | None = None
    extra: list[str] = []
    for att in message.attachments:
        if media is None and (att.content_type or "").startswith("image/"):
            media = {
                "url": att.url,
                "thumbnail_url": att.url,
                "type": "image",
                "width": att.width,
                "height": att.height,
                "alt": att.filename[:256],
            }
        else:
            extra.append(att.url)
    if extra:
        content = f"{content}\n{'\n'.join(extra)}".strip()
    if not content and not media:
        return None
    if len(content) > MAX_CONTENT:
        content = content[: MAX_CONTENT - 1] + "…"
    created_at = message.created_at
    if created_at.tzinfo is None:  # discord.py always returns tz-aware, but be safe
        created_at = created_at.replace(tzinfo=UTC)
    return {
        "sender": sender_slug(message.author),
        "content": content,
        "media": media,
        "created_at": int(created_at.timestamp() * 1000),
    }


class MirrorBot:
    """Forwards live Discord guild messages into apehost chat channels."""

    def __init__(
        self,
        token: str,
        guild_id: int,
        bridge_url: str,
        bridge_token: str,
    ) -> None:
        self.token = token
        self.guild_id = guild_id
        self.bridge_url = bridge_url.rstrip("/")
        self.bridge_token = bridge_token
        self._rooms: dict[int, str] = {}
        self._session: aiohttp.ClientSession | None = None

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    async def on_ready(self) -> None:
        print(f"Mirror bot connected as {self.client.user} (guild {self.guild_id})")

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any] | None:
        assert self._session is not None
        try:
            async with self._session.post(f"{self.bridge_url}/{path}", json=body) as resp:
                if resp.status >= 400:
                    text = (await resp.text())[:200]
                    logger.warning("bridge %s failed: %s %s", path, resp.status, text)
                    return None
                return await resp.json() if resp.content_length else None
        except aiohttp.ClientError as e:
            logger.warning("bridge %s unreachable: %s", path, e)
            return None

    async def _room_id(
        self, channel: discord.TextChannel | discord.VoiceChannel
    ) -> str | None:
        """Find-or-create the chat channel mirroring a Discord channel."""
        cached = self._rooms.get(channel.id)
        if cached:
            return cached
        assert self._session is not None
        name = mirror_channel_name(channel.name)
        try:
            async with self._session.get(f"{self.bridge_url}/channels") as resp:
                if resp.status != 200:
                    logger.warning("bridge channel list failed: %s", resp.status)
                    return None
                channels = (await resp.json()).get("channels", [])
        except aiohttp.ClientError as e:
            logger.warning("bridge channel list unreachable: %s", e)
            return None
        room_id = next((str(c["id"]) for c in channels if c.get("name") == name), None)
        if room_id is None:
            created = await self._post(
                "create-channel",
                {"name": name, "topic": f"Mirror of Discord #{channel.name}"[:200]},
            )
            if not created or "channel" not in created:
                return None
            room_id = created["channel"]["id"]
        self._rooms[channel.id] = room_id
        return room_id

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None or message.guild.id != self.guild_id:
            return
        if isinstance(message.channel, discord.Thread):
            return  # ponytail: threads not mirrored in v1; add a thread->chan map if wanted
        payload = build_payload(message)
        if payload is None:
            return
        # Runtime-checked to be a guild text/voice channel (threads and DMs return above).
        room_id = await self._room_id(message.channel)  # type: ignore[arg-type]
        if room_id is None:
            return
        payload["room_id"] = room_id
        await self._post("send", payload)

    async def run(self) -> None:
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.bridge_token}"},
        ) as session:
            self._session = session
            await self.client.start(self.token)

    def run_sync(self) -> None:
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            print("\nMirror stopped.")
