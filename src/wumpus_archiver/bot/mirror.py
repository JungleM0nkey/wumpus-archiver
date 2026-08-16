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
from urllib.parse import urlsplit

import aiohttp
import discord

logger = logging.getLogger(__name__)

BRIDGE_SENDER_PREFIX = "discord-"
MAX_CONTENT = 4000  # must match the chat Worker's cap
MAX_CHANNEL_NAME = 64  # must match the chat Worker's validChannelName

# Mirror the chat Worker's MEDIA_HOST allowlist (dashboard/src/worker/chat.ts
# allowedMediaUrl). The bridge rejects a send with off-allowlist media WHOLESALE
# (parseBridgeSendBody returns null), so gate here: off-allowlist visuals fall
# back to a URL line in the content instead of killing the mirrored message.
_ALLOWED_MEDIA_HOSTS = frozenset(
    {
        "gifs.connect.apehost.net",
        "media.tenor.com",
        "c.tenor.com",
        "i.imgur.com",
        "cdn.discordapp.com",
        "media.discordapp.net",
        "static.klipy.com",
    }
)
_ALLOWED_MEDIA_SUFFIXES = (".giphy.com",)

_VIDEO_EXT = re.compile(r"\.(mp4|webm|mov|m4v|gifv)$", re.IGNORECASE)
_VISUAL_EXT = re.compile(r"\.(gif|jpe?g|png|webp|avif|mp4|webm|mov|m4v)$", re.IGNORECASE)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _allowed_media_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = parts.hostname or ""
    return parts.scheme == "https" and (
        host in _ALLOWED_MEDIA_HOSTS or host.endswith(_ALLOWED_MEDIA_SUFFIXES)
    )


def _is_visual(url: str, content_type: str | None) -> bool:
    """True for an attachment we can render (image or video), by type or extension."""
    ct = content_type or ""
    return ct.startswith(("image/", "video/")) or bool(_VISUAL_EXT.search(url.split("?", 1)[0]))


def _media_kind(url: str, content_type: str | None) -> str:
    """Advisory 'video' | 'gif' | 'image' (the chat client re-sniffs on render)."""
    if (content_type or "").startswith("video/"):
        return "video"
    path = url.split("?", 1)[0]
    if _VIDEO_EXT.search(path):
        return "video"
    if path.lower().endswith(".gif") or content_type == "image/gif":
        return "gif"
    return "image"


def _media_dict(
    url: str,
    kind: str,
    poster: str = "",
    width: int | None = None,
    height: int | None = None,
    alt: str = "",
) -> dict[str, Any]:
    # poster off-allowlist: the Worker's validMedia degrades it back to url.
    return {
        "url": url,
        "thumbnail_url": poster or url,
        "type": kind,
        "width": width,
        "height": height,
        "alt": alt[:256],
    }


def _embed_visuals(embed: dict[str, Any]) -> tuple[str, str, str]:
    """(video_url, image_url, poster_url) from an embed dict ('' when absent).

    Accepts discord.py's ``to_dict()`` shape (live mirror) and the same JSON
    stored in the archive (backfill) — both prefer proxy_url for images since
    Discord CDN signed urls expire.
    """
    video = embed.get("video") or {}
    image = embed.get("image") or {}
    thumb = embed.get("thumbnail") or {}
    video_url = video.get("url") or video.get("proxy_url") or ""
    image_url = image.get("proxy_url") or image.get("url") or ""
    poster = thumb.get("proxy_url") or thumb.get("url") or ""
    return video_url, image_url, poster


def sender_slug(name: str, global_name: str | None = None) -> str:
    """Stable chat slug for a Discord author: ``discord-<sanitized name>``."""
    display = global_name or name or "user"
    slug = _SLUG_STRIP.sub("-", display.lower()).strip("-")[:32].strip("-")
    return f"{BRIDGE_SENDER_PREFIX}{slug or 'user'}"


def mirror_channel_name(channel_name: str) -> str:
    """Chat channel name for a Discord channel: ``discord-<name>``, capped."""
    return f"{BRIDGE_SENDER_PREFIX}{channel_name}".strip()[:MAX_CHANNEL_NAME]


def build_media_payload(
    content: str,
    attachments: list[dict[str, Any]],
    embeds: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    """Neutral core shared by the live mirror and the archive backfill.

    ``attachments``: dicts with url/content_type/width/height/filename.
    ``embeds``: discord.py to_dict() shape (also the archive's stored JSON).
    The first renderable visual — an image/video attachment, or a GIF/image
    embed (Tenor & friends) on an allowlisted media host — becomes the message
    media. Everything else (non-visual attachments, extra visuals, embed URLs)
    is appended to the content as URL lines, which the chat client renders as
    clickable links. Returns (content, media).
    """
    media: dict[str, Any] | None = None
    extra: list[str] = []

    for att in attachments:
        url = att["url"]
        ct = att.get("content_type")
        if media is None and _is_visual(url, ct) and _allowed_media_url(url):
            media = _media_dict(
                url,
                _media_kind(url, ct),
                width=att.get("width"),
                height=att.get("height"),
                alt=att.get("filename") or "",
            )
        else:
            extra.append(url)

    for embed in embeds:
        video_url, image_url, poster = _embed_visuals(embed)
        if media is None and video_url and _allowed_media_url(video_url):
            # GIF-style embed: image/thumbnail are previews of the same visual.
            media = _media_dict(video_url, "video", poster=poster)
            continue
        if media is None and image_url and _allowed_media_url(image_url):
            media = _media_dict(image_url, _media_kind(image_url, None), poster=poster)
            continue
        # No media slot left, or the hosts are off-allowlist: keep links clickable.
        if video_url:
            extra.append(video_url)
        if image_url and image_url != poster:
            extra.append(image_url)
        link = embed.get("url") or ""
        if link and link not in content and link not in extra:
            extra.append(link)

    if extra:
        content = f"{content}\n{'\n'.join(extra)}".strip()
    return content, media


def _attachment_dict(att: Any) -> dict[str, Any]:
    return {
        "url": att.url,
        "content_type": getattr(att, "content_type", None),
        "width": getattr(att, "width", None),
        "height": getattr(att, "height", None),
        "filename": getattr(att, "filename", "") or "",
    }


def _embed_dict(embed: Any) -> dict[str, Any]:
    to_dict = getattr(embed, "to_dict", None)
    return to_dict() if callable(to_dict) else dict(embed)


def build_payload(message: discord.Message) -> dict[str, Any] | None:
    """Build a bridge send body from a Discord message, or None if not mirrorable.

    Thin adapter over :func:`build_media_payload` (the shared visual/embed
    selection core); see its docstring for the media/URL-line policy.
    """
    content, media = build_media_payload(
        message.clean_content.strip(),
        [_attachment_dict(att) for att in message.attachments],
        [_embed_dict(embed) for embed in getattr(message, "embeds", None) or []],
    )
    if not content and not media:
        return None
    if len(content) > MAX_CONTENT:
        content = content[: MAX_CONTENT - 1] + "…"
    created_at = message.created_at
    if created_at.tzinfo is None:  # discord.py always returns tz-aware, but be safe
        created_at = created_at.replace(tzinfo=UTC)
    return {
        "sender": sender_slug(message.author.name, message.author.global_name),
        "content": content,
        "media": media,
        "created_at": int(created_at.timestamp() * 1000),
    }


class BridgeClient:
    """HTTP client for the dashboard Worker's chat bridge (secret + optional
    Cloudflare Access edge passage). Shared by the live mirror and backfill."""

    def __init__(
        self,
        bridge_url: str,
        bridge_token: str,
        cf_access_client_id: str = "",
        cf_access_client_secret: str = "",
    ) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self.bridge_token = bridge_token
        self.cf_access_client_id = cf_access_client_id
        self.cf_access_client_secret = cf_access_client_secret
        self._rooms: dict[str, str] = {}  # chat channel name -> room id
        self._session: aiohttp.ClientSession | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.bridge_token}"}
        if self.cf_access_client_id and self.cf_access_client_secret:
            # Edge passage through the Cloudflare Access app in front of connect.apehost.net.
            headers["CF-Access-Client-Id"] = self.cf_access_client_id
            headers["CF-Access-Client-Secret"] = self.cf_access_client_secret
        return headers

    async def __aenter__(self) -> "BridgeClient":
        self._session = aiohttp.ClientSession(headers=self._headers())
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any] | None:
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

    async def room_for(self, name: str, topic: str) -> str | None:
        """Find-or-create a chat channel by exact name. Cached per process."""
        cached = self._rooms.get(name)
        if cached:
            return cached
        assert self._session is not None
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
            created = await self.post("create-channel", {"name": name, "topic": topic[:200]})
            if not created or "channel" not in created:
                return None
            room_id = created["channel"]["id"]
        self._rooms[name] = room_id
        return room_id

    async def put_users(self, entries: list[dict[str, str]]) -> dict[str, Any] | None:
        """Upsert Discord sender directory entries (slug/display_name/avatar_url)."""
        return await self.post("users", {"users": entries})


def user_entry(user: Any) -> dict[str, str] | None:
    """Bridge directory entry for a Discord user, or None if it cannot be built."""
    name = getattr(user, "name", None) or ""
    global_name = getattr(user, "global_name", None)
    display = (global_name or name or "user").strip()
    if not display:
        return None
    avatar = getattr(user, "avatar", None)
    avatar_url = str(avatar.url) if avatar else ""
    return {
        "slug": sender_slug(name, global_name),
        "display_name": display[:64],
        "avatar_url": avatar_url,
    }


class MirrorBot:
    """Forwards live Discord guild messages into apehost chat channels."""

    def __init__(self, token: str, guild_id: int, bridge: BridgeClient) -> None:
        self.token = token
        self.guild_id = guild_id
        self.bridge = bridge
        self._user_cache: dict[int, tuple[str, str]] = {}  # discord id -> (display, avatar)

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    async def on_ready(self) -> None:
        print(f"Mirror bot connected as {self.client.user} (guild {self.guild_id})", flush=True)

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
        await self._push_user(message.author)
        # Guild-checked above; union still includes DM/partial channels without names.
        chan_name = getattr(message.channel, "name", None) or "unknown"
        room_id = await self.bridge.room_for(
            mirror_channel_name(chan_name),
            f"Mirror of Discord #{chan_name}",
        )
        if room_id is None:
            return
        payload["room_id"] = room_id
        await self.bridge.post("send", payload)

    async def _push_user(self, author: Any) -> None:
        """Keep the Worker's discord-user directory fresh: push on first sight or change."""
        entry = user_entry(author)
        if entry is None:
            return
        try:
            discord_id = int(author.id)
        except (AttributeError, ValueError, TypeError):
            return
        sig = (entry["display_name"], entry["avatar_url"])
        if self._user_cache.get(discord_id) == sig:
            return
        if await self.bridge.put_users([entry]):
            self._user_cache[discord_id] = sig

    async def run(self) -> None:
        await self.client.start(self.token)

    def run_sync(self) -> None:
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            print("\nMirror stopped.")
