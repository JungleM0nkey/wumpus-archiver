"""BridgeClient must validate its URL up front and never follow redirects.

The client sends a bearer token plus Cloudflare Access ``CF-Access-Client-*`` headers on every
request. aiohttp strips ``Authorization`` when a redirect leaves the origin but forwards custom
headers (and a 307/308 keeps the POST body), so following a redirect from a compromised or
misconfigured bridge would hand the Cloudflare Access credentials to another host.

All servers bind to 127.0.0.1 on an ephemeral port; every credential below is a fake.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from wumpus_archiver.bot.mirror import BridgeClient

BRIDGE_TOKEN = "fake-bridge-token-BBBB2222"
CF_ID = "fake-cf-id-DDDD4444"
CF_SECRET = "fake-cf-secret-CCCC3333"
SECRETS = (BRIDGE_TOKEN, CF_ID, CF_SECRET)

REDIRECT_STATUSES = [301, 302, 303, 307, 308]


@dataclass
class Hit:
    """One request a test server received."""

    method: str
    path: str
    headers: dict[str, str]


@dataclass
class OtherOrigin:
    """Server B: a different origin that records every request it receives."""

    url: str = ""
    hits: list[Hit] = field(default_factory=list)


@dataclass
class RedirectingBridge:
    """Server A: a bridge whose endpoints answer with a configurable status.

    For 3xx statuses the ``Location`` points either at server B (``cross``) or back at
    another path on this same server (``same``).
    """

    url: str = ""  # the bridge base URL, http://127.0.0.1:<port>/bridge
    origin: str = ""
    status: int = 200
    target: str = "cross"
    other: OtherOrigin = field(default_factory=OtherOrigin)
    requests: list[Hit] = field(default_factory=list)  # requests to the bridge endpoints
    followed: list[Hit] = field(default_factory=list)  # requests to the same-origin target

    def landed(self) -> list[Hit]:
        """Requests that arrived at the redirect target, wherever it was."""
        return self.other.hits if self.target == "cross" else self.followed

    def location(self) -> str:
        if self.target == "cross":
            return f"{self.other.url}/stolen"
        return f"{self.origin}/bridge/elsewhere"


def _hit(request: web.Request) -> Hit:
    return Hit(request.method, request.path, dict(request.headers))


@pytest.fixture
async def other_origin() -> AsyncIterator[OtherOrigin]:
    """Serve a catch-all on 127.0.0.1 that is reached as ``localhost`` (a different origin)."""
    other = OtherOrigin()

    async def handler(request: web.Request) -> web.Response:
        other.hits.append(_hit(request))
        return web.json_response({"channels": [], "ok": True})

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    other.url = f"http://localhost:{server.port}"
    try:
        yield other
    finally:
        await server.close()


@pytest.fixture
async def bridge(other_origin: OtherOrigin) -> AsyncIterator[RedirectingBridge]:
    """Serve a bridge on 127.0.0.1 (``/bridge/channels``, ``/bridge/<anything>``)."""
    state = RedirectingBridge(other=other_origin)

    async def respond(request: web.Request) -> web.Response:
        state.requests.append(_hit(request))
        if 300 <= state.status < 400:
            return web.Response(status=state.status, headers={"Location": state.location()})
        if state.status >= 400:
            return web.Response(status=state.status, text="bridge says no")
        return web.json_response({"ok": True, "channels": []})

    async def elsewhere(request: web.Request) -> web.Response:
        state.followed.append(_hit(request))
        return web.json_response({"channels": [], "ok": True})

    app = web.Application()
    app.router.add_get("/bridge/channels", respond)
    app.router.add_post("/bridge/{path}", respond)
    app.router.add_route("*", "/bridge/elsewhere", elsewhere)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    state.origin = f"http://127.0.0.1:{server.port}"
    state.url = f"{state.origin}/bridge"
    try:
        yield state
    finally:
        await server.close()


def _client(bridge: RedirectingBridge) -> BridgeClient:
    return BridgeClient(bridge.url, BRIDGE_TOKEN, CF_ID, CF_SECRET)


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    """Everything every logger emitted, fully formatted."""
    parts = []
    for record in caplog.records:
        parts.append(record.getMessage())
        if record.exc_text:
            parts.append(record.exc_text)
    return "\n".join(parts)


def _assert_log_is_clean(caplog: pytest.LogCaptureFixture, bridge: RedirectingBridge) -> None:
    """No credential, redirect target or header name may appear in any log record."""
    text = _logged(caplog)
    for secret in SECRETS:
        assert secret not in text
    assert bridge.location() not in text
    assert bridge.other.url not in text
    assert "stolen" not in text
    assert "elsewhere" not in text
    assert "location" not in text.lower()


async def test_harness_detects_followed_redirects(bridge: RedirectingBridge) -> None:
    """Control: aiohttp's default behaviour does reach the redirect target.

    Guards the tests below against passing vacuously (e.g. a broken second server).
    """
    bridge.status = 307
    async with (
        aiohttp.ClientSession(headers={"CF-Access-Client-Id": CF_ID}) as session,
        session.post(f"{bridge.url}/send", json={}) as resp,
    ):
        assert resp.status == 200
    assert [h.method for h in bridge.other.hits] == ["POST"]


@pytest.mark.parametrize("target", ["cross", "same"])
@pytest.mark.parametrize("status", REDIRECT_STATUSES)
class TestRedirectsAreRefused:
    """A 3xx from the bridge is never followed, to another origin or to the same one."""

    async def test_post_returns_none(
        self,
        bridge: RedirectingBridge,
        status: int,
        target: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        bridge.status, bridge.target = status, target
        caplog.set_level(logging.DEBUG)

        async with _client(bridge) as client:
            result = await client.post("send", {"content": "hi", "sender": "discord-alice"})

        assert result is None
        # The credentials went to the configured bridge, once, and nowhere else
        assert [h.path for h in bridge.requests] == ["/bridge/send"]
        assert bridge.requests[0].headers["Authorization"] == f"Bearer {BRIDGE_TOKEN}"
        assert bridge.requests[0].headers["CF-Access-Client-Secret"] == CF_SECRET
        assert bridge.landed() == []

        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("send" in m and str(status) in m for m in warnings), warnings
        _assert_log_is_clean(caplog, bridge)

    async def test_room_for_returns_none(
        self,
        bridge: RedirectingBridge,
        status: int,
        target: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        bridge.status, bridge.target = status, target
        caplog.set_level(logging.DEBUG)

        async with _client(bridge) as client:
            room = await client.room_for("discord-general", "A topic")

        assert room is None
        # Only the channel listing was attempted: no create-channel POST, no follow-up request
        assert [(h.method, h.path) for h in bridge.requests] == [("GET", "/bridge/channels")]
        assert bridge.landed() == []

        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("channel" in m and str(status) in m for m in warnings), warnings
        _assert_log_is_clean(caplog, bridge)


class TestOtherStatusesUnchanged:
    """Only 3xx handling is new; success and error responses behave as before."""

    async def test_success_still_returns_json(self, bridge: RedirectingBridge) -> None:
        bridge.status = 200
        async with _client(bridge) as client:
            assert await client.post("send", {"content": "hi"}) == {"ok": True, "channels": []}
        assert bridge.other.hits == []

    @pytest.mark.parametrize("status", [400, 404, 500])
    async def test_error_status_returns_none_and_logs_it(
        self, bridge: RedirectingBridge, status: int, caplog: pytest.LogCaptureFixture
    ) -> None:
        bridge.status = status
        caplog.set_level(logging.DEBUG)
        async with _client(bridge) as client:
            assert await client.post("send", {"content": "hi"}) is None
            assert await client.room_for("discord-general", "t") is None
        messages = _logged(caplog)
        assert f"bridge send failed: {status}" in messages
        assert f"bridge channel list failed: {status}" in messages
        for secret in SECRETS:
            assert secret not in messages


class TestUrlIsValidatedAtConstruction:
    """The client fails closed for any caller, whatever Settings let through."""

    def test_plain_http_remote_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must use https"):
            BridgeClient("http://remote.example/x", "t")

    @pytest.mark.parametrize(
        "url",
        [
            "https://remote.example/x",
            "HTTPS://remote.example:8443/x",
            "http://127.0.0.1/bridge",
            "http://127.0.0.1:8787/bridge",
            "http://localhost:8787/bridge",
            "http://[::1]:8787/bridge",
        ],
    )
    def test_https_and_loopback_http_construct(self, url: str) -> None:
        assert BridgeClient(url, "t").bridge_url == url

    def test_url_is_normalised(self) -> None:
        client = BridgeClient("  https://remote.example/x/ \n", "t")
        assert client.bridge_url == "https://remote.example/x"

    @pytest.mark.parametrize(
        "url",
        [
            "http://remote.example/x",
            "ftp://remote.example/x",
            "remote.example/x",
            "",
            "https://user:SECRETMARK@remote.example/x",
            "http://user:SECRETMARK@127.0.0.1:8787/x",
            "https://remote.example:99999/x",
            "https://remote.example:SECRETMARK/x",
        ],
    )
    def test_bad_urls_raise_without_echoing_anything(self, url: str) -> None:
        with pytest.raises(ValueError) as exc_info:
            BridgeClient(url, BRIDGE_TOKEN, CF_ID, CF_SECRET)
        shown = f"{exc_info.value} {exc_info.value.__cause__} {exc_info.value.__context__}"
        for secret in (*SECRETS, "SECRETMARK", "remote.example"):
            assert secret not in shown
        assert exc_info.value.__context__ is None
