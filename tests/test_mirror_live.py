"""Tests for the live mirror path: Discord message -> BridgeClient -> HTTP bridge.

The existing mirror tests stub out ``MirrorBot`` / ``BridgeClient``. These run the real classes
against a local fake bridge so a missing session (see issue #26) cannot slip through again.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from wumpus_archiver.bot.mirror import BridgeClient, MirrorBot

BRIDGE_TOKEN = "test-bridge-token"
DISCORD_TOKEN = "fake-discord-token"
GUILD_ID = 42


class FakeBridge:
    """Records what the mirror sends to a local stand-in for the chat bridge."""

    def __init__(self) -> None:
        self.channel_lists = 0
        self.created: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self.users: list[dict[str, Any]] = []
        self.auth_headers: list[str | None] = []
        self.url = ""


@pytest.fixture
async def fake_bridge() -> AsyncIterator[FakeBridge]:
    """Serve a minimal chat bridge (channels, create-channel, send, users) on localhost."""
    bridge = FakeBridge()

    async def list_channels(request: web.Request) -> web.Response:
        bridge.auth_headers.append(request.headers.get("Authorization"))
        bridge.channel_lists += 1
        return web.json_response({"channels": []})

    async def create_channel(request: web.Request) -> web.Response:
        body = await request.json()
        bridge.created.append(body)
        return web.json_response({"channel": {"id": "room-1", "name": body["name"]}})

    async def send(request: web.Request) -> web.Response:
        bridge.sent.append(await request.json())
        return web.json_response({"ok": True})

    async def users(request: web.Request) -> web.Response:
        body = await request.json()
        bridge.users.extend(body["users"])
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/bridge/channels", list_channels)
    app.router.add_post("/bridge/create-channel", create_channel)
    app.router.add_post("/bridge/send", send)
    app.router.add_post("/bridge/users", users)
    server = TestServer(app)
    await server.start_server()
    bridge.url = str(server.make_url("/bridge"))
    try:
        yield bridge
    finally:
        await server.close()


def _guild_message(content: str = "hello world") -> SimpleNamespace:
    """A minimal stand-in for a discord.Message in the mirrored guild."""
    return SimpleNamespace(
        author=SimpleNamespace(bot=False, id=123, name="alice", global_name="Alice", avatar=None),
        guild=SimpleNamespace(id=GUILD_ID),
        channel=SimpleNamespace(name="general"),
        clean_content=content,
        attachments=[],
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


class TestLiveMirrorForwarding:
    """MirrorBot.run() must keep the BridgeClient session open while Discord is connected."""

    async def test_message_reaches_the_bridge(
        self, fake_bridge: FakeBridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A guild message seen while connected is forwarded to the bridge."""
        bridge = BridgeClient(fake_bridge.url, BRIDGE_TOKEN)
        bot = MirrorBot(DISCORD_TOKEN, GUILD_ID, bridge)

        async def fake_start(token: str) -> None:
            # Stands in for the Discord gateway loop: a message arrives while connected.
            assert token == DISCORD_TOKEN
            await bot.on_message(_guild_message())

        monkeypatch.setattr(bot.client, "start", fake_start)

        await bot.run()

        assert [c["name"] for c in fake_bridge.created] == ["discord-general"]
        assert len(fake_bridge.sent) == 1
        sent = fake_bridge.sent[0]
        assert sent["room_id"] == "room-1"
        assert sent["sender"] == "discord-alice"
        assert sent["content"] == "hello world"
        assert [u["slug"] for u in fake_bridge.users] == ["discord-alice"]

    async def test_requests_carry_the_bridge_token(
        self, fake_bridge: FakeBridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The session opened by run() sends the bearer token on bridge requests."""
        bridge = BridgeClient(fake_bridge.url, BRIDGE_TOKEN)
        bot = MirrorBot(DISCORD_TOKEN, GUILD_ID, bridge)

        async def fake_start(token: str) -> None:
            await bot.on_message(_guild_message())

        monkeypatch.setattr(bot.client, "start", fake_start)

        await bot.run()

        assert fake_bridge.auth_headers == [f"Bearer {BRIDGE_TOKEN}"]

    async def test_session_is_closed_after_run(
        self, fake_bridge: FakeBridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The session exists while connected and is released once run() returns."""
        bridge = BridgeClient(fake_bridge.url, BRIDGE_TOKEN)
        bot = MirrorBot(DISCORD_TOKEN, GUILD_ID, bridge)
        open_while_connected: list[bool] = []

        async def fake_start(token: str) -> None:
            open_while_connected.append(bridge._session is not None)

        monkeypatch.setattr(bot.client, "start", fake_start)

        await bot.run()

        assert open_while_connected == [True]
        assert bridge._session is None

    async def test_session_is_closed_when_login_fails(
        self, fake_bridge: FakeBridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed Discord login propagates and still releases the bridge session."""
        bridge = BridgeClient(fake_bridge.url, BRIDGE_TOKEN)
        bot = MirrorBot(DISCORD_TOKEN, GUILD_ID, bridge)

        async def fake_start(token: str) -> None:
            assert bridge._session is not None
            raise discord.LoginFailure("Improper token has been passed.")

        monkeypatch.setattr(bot.client, "start", fake_start)

        with pytest.raises(discord.LoginFailure):
            await bot.run()

        assert bridge._session is None
