"""Tests for API authentication on scrape control and the CORS policy."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError

from wumpus_archiver.api.app import create_app
from wumpus_archiver.api.deps import wiring_of
from wumpus_archiver.api.scrape_manager import JobStatus, ScrapeJob, ScrapeJobManager
from wumpus_archiver.cli import _warn_if_not_loopback
from wumpus_archiver.compose import api_security_from_settings
from wumpus_archiver.config import DEFAULT_CORS_ORIGINS, Settings
from wumpus_archiver.storage.database import Database

# Obvious fakes, never real credentials
API_TOKEN = "test-api-token-not-a-real-secret"
DISCORD_TOKEN = "fake-discord-token"
ALLOWED_ORIGIN = "http://localhost:5173"
EVIL_ORIGIN = "https://evil.example"
AB_ORIGINS = ["https://a.example", "https://b.example"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate tests from the developer's environment and any ``.env`` in the cwd."""
    for var in ("API_AUTH_TOKEN", "CORS_ORIGINS", "DISCORD_BOT_TOKEN", "LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def start_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Replace the scrape manager's start/cancel so no Discord connection is attempted."""
    calls: list[tuple[int, str]] = []

    def fake_start(self: ScrapeJobManager, guild_id: int) -> ScrapeJob:
        calls.append((guild_id, self._token))
        return ScrapeJob(
            id="job123",
            guild_id=guild_id,
            status=JobStatus.PENDING,
            started_at=datetime.now(UTC),
        )

    monkeypatch.setattr(ScrapeJobManager, "start_scrape", fake_start)
    monkeypatch.setattr(ScrapeJobManager, "cancel", lambda self: True)
    return calls


def make_app(database: Database, *, api_auth_token: str | None = None) -> FastAPI:
    """An app with scrape control configured, the given API token and the default origins.

    This is what ``serve`` hands ``create_app`` when the bot token is set, ``CORS_ORIGINS``
    is unset and ``API_AUTH_TOKEN`` is ``api_auth_token``.
    """
    return create_app(
        database,
        scrape=ScrapeJobManager(database, DISCORD_TOKEN),
        api_auth_token=api_auth_token,
        cors_origins=DEFAULT_CORS_ORIGINS,
    )


def app_as_serve_builds_it(database: Database) -> FastAPI:
    """The app composed the way ``serve`` composes it: the API token and origins from settings."""
    api_auth_token, cors_origins = api_security_from_settings()
    return create_app(
        database,
        scrape=ScrapeJobManager(database, DISCORD_TOKEN),
        api_auth_token=api_auth_token,
        cors_origins=cors_origins,
    )


def wired_token(app: FastAPI) -> str | None:
    """The API token the app was built with, revealed."""
    token = wiring_of(app).api_auth_token
    return token.get_secret_value() if token is not None else None


def client_for(app: FastAPI) -> httpx.AsyncClient:
    """Build an in-process HTTP client for the app (lifespan is not run)."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


def bearer(token: str) -> dict[str, str]:
    """Build an Authorization header."""
    return {"Authorization": f"Bearer {token}"}


START_BODY = {"guild_id": 123456789}


class TestScrapeControlDisabled:
    """No API_AUTH_TOKEN configured: state-changing endpoints fail closed."""

    async def test_start_returns_403(
        self, database: Database, start_calls: list[tuple[int, str]]
    ) -> None:
        app = make_app(database)
        async with client_for(app) as client:
            resp = await client.post("/api/scrape/start", json=START_BODY)
        assert resp.status_code == 403
        assert "API_AUTH_TOKEN" in resp.json()["detail"]
        assert start_calls == []

    async def test_cancel_returns_403(self, database: Database) -> None:
        app = make_app(database)
        async with client_for(app) as client:
            resp = await client.post("/api/scrape/cancel")
        assert resp.status_code == 403
        assert "API_AUTH_TOKEN" in resp.json()["detail"]

    async def test_bearer_header_does_not_bypass(
        self, database: Database, start_calls: list[tuple[int, str]]
    ) -> None:
        app = make_app(database)
        async with client_for(app) as client:
            for token in ("", "anything", "None"):
                resp = await client.post(
                    "/api/scrape/start", json=START_BODY, headers=bearer(token)
                )
                assert resp.status_code == 403
        assert start_calls == []

    async def test_empty_env_token_is_disabled(
        self,
        database: Database,
        monkeypatch: pytest.MonkeyPatch,
        start_calls: list[tuple[int, str]],
    ) -> None:
        monkeypatch.setenv("API_AUTH_TOKEN", "")
        app = app_as_serve_builds_it(database)
        assert wired_token(app) is None
        async with client_for(app) as client:
            resp = await client.post("/api/scrape/start", json=START_BODY, headers=bearer(""))
        assert resp.status_code == 403
        assert start_calls == []

    async def test_status_reports_control_disabled(self, database: Database) -> None:
        app = make_app(database)
        async with client_for(app) as client:
            resp = await client.get("/api/scrape/status")
        assert resp.status_code == 200
        assert resp.json()["control_enabled"] is False


class TestScrapeControlEnabled:
    """API_AUTH_TOKEN configured: bearer token required for start/cancel."""

    @pytest.mark.parametrize("path", ["/api/scrape/start", "/api/scrape/cancel"])
    async def test_missing_header_returns_401(
        self, database: Database, start_calls: list[tuple[int, str]], path: str
    ) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            resp = await client.post(path, json=START_BODY)
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"
        assert start_calls == []

    @pytest.mark.parametrize(
        "header",
        [
            f"Basic {API_TOKEN}",
            f"Token {API_TOKEN}",
            API_TOKEN,
            "Bearer",
            "Bearer   ",
        ],
    )
    async def test_malformed_header_returns_401(
        self, database: Database, start_calls: list[tuple[int, str]], header: str
    ) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            resp = await client.post(
                "/api/scrape/start", json=START_BODY, headers={"Authorization": header}
            )
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"
        assert start_calls == []

    @pytest.mark.parametrize("path", ["/api/scrape/start", "/api/scrape/cancel"])
    async def test_wrong_token_returns_401(
        self, database: Database, start_calls: list[tuple[int, str]], path: str
    ) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        wrong = "x" * len(API_TOKEN)  # same length: must still be rejected
        async with client_for(app) as client:
            resp = await client.post(path, json=START_BODY, headers=bearer(wrong))
            prefix = await client.post(path, json=START_BODY, headers=bearer(API_TOKEN[:-1]))
        assert resp.status_code == 401
        assert prefix.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"
        assert wrong not in resp.text
        assert API_TOKEN not in resp.text
        assert start_calls == []

    async def test_non_ascii_token_returns_401_not_500(self, database: Database) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            resp = await client.post(
                "/api/scrape/start",
                json=START_BODY,
                headers={"Authorization": "Bearer pässwörd-ñ".encode()},
            )
        assert resp.status_code == 401

    async def test_correct_token_starts_scrape(
        self, database: Database, start_calls: list[tuple[int, str]]
    ) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            resp = await client.post(
                "/api/scrape/start", json=START_BODY, headers=bearer(API_TOKEN)
            )
        assert resp.status_code == 202
        assert resp.json()["job"]["id"] == "job123"
        assert start_calls == [(START_BODY["guild_id"], DISCORD_TOKEN)]

    async def test_scheme_is_case_insensitive(
        self, database: Database, start_calls: list[tuple[int, str]]
    ) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            resp = await client.post(
                "/api/scrape/start",
                json=START_BODY,
                headers={"Authorization": f"bearer {API_TOKEN}"},
            )
        assert resp.status_code == 202
        assert len(start_calls) == 1

    async def test_correct_token_cancels_scrape(
        self, database: Database, start_calls: list[tuple[int, str]]
    ) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            resp = await client.post("/api/scrape/cancel", headers=bearer(API_TOKEN))
        assert resp.status_code == 200
        assert resp.json() == {"message": "Cancellation requested"}

    async def test_correct_token_cancel_without_job_is_404(self, database: Database) -> None:
        """Auth passes, so the endpoint's own logic answers (nothing to cancel)."""
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            resp = await client.post("/api/scrape/cancel", headers=bearer(API_TOKEN))
        assert resp.status_code == 404

    async def test_read_endpoints_stay_open(self, database: Database) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            status = await client.get("/api/scrape/status")
            history = await client.get("/api/scrape/history")
            guilds = await client.get("/api/guilds")
        assert status.status_code == 200
        assert status.json()["control_enabled"] is True
        assert API_TOKEN not in status.text
        assert history.status_code == 200
        assert history.json() == {"jobs": []}
        assert guilds.status_code == 200

    async def test_token_from_environment(
        self,
        database: Database,
        monkeypatch: pytest.MonkeyPatch,
        start_calls: list[tuple[int, str]],
    ) -> None:
        """API_AUTH_TOKEN is picked up even though DISCORD_BOT_TOKEN is not set."""
        monkeypatch.setenv("API_AUTH_TOKEN", API_TOKEN)
        app = app_as_serve_builds_it(database)
        async with client_for(app) as client:
            denied = await client.post("/api/scrape/start", json=START_BODY)
            ok = await client.post("/api/scrape/start", json=START_BODY, headers=bearer(API_TOKEN))
        assert denied.status_code == 401
        assert ok.status_code == 202

    async def test_token_from_dotenv_file(
        self,
        database: Database,
        tmp_path: Path,
        start_calls: list[tuple[int, str]],
    ) -> None:
        (tmp_path / ".env").write_text(f"API_AUTH_TOKEN={API_TOKEN}\n")
        app = app_as_serve_builds_it(database)
        async with client_for(app) as client:
            ok = await client.post("/api/scrape/start", json=START_BODY, headers=bearer(API_TOKEN))
        assert ok.status_code == 202

    async def test_create_app_never_reads_the_token_from_the_environment(
        self, database: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Only the composition root reads API_AUTH_TOKEN; the factory uses what it is handed."""
        monkeypatch.setenv("API_AUTH_TOKEN", "env-token")
        (tmp_path / ".env").write_text("API_AUTH_TOKEN=dotenv-token\n")
        assert wired_token(make_app(database, api_auth_token=API_TOKEN)) == API_TOKEN
        assert wired_token(make_app(database)) is None

    async def test_env_fallback_when_settings_are_invalid(
        self,
        database: Database,
        monkeypatch: pytest.MonkeyPatch,
        start_calls: list[tuple[int, str]],
    ) -> None:
        """Unrelated invalid settings must not silently drop the configured token."""
        monkeypatch.setenv("LOG_LEVEL", "bogus")
        monkeypatch.setenv("API_AUTH_TOKEN", API_TOKEN)
        app = app_as_serve_builds_it(database)
        assert wired_token(app) == API_TOKEN

    async def test_the_token_never_shows_in_a_repr(self, database: Database) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        assert API_TOKEN not in repr(wiring_of(app))

    async def test_a_blank_token_handed_in_disables_control(self, database: Database) -> None:
        app = make_app(database, api_auth_token="   ")
        assert wired_token(app) is None
        async with client_for(app) as client:
            resp = await client.post("/api/scrape/start", json=START_BODY, headers=bearer("   "))
        assert resp.status_code == 403


class TestCors:
    """CORS policy: configured origins only, no credentials, limited methods/headers."""

    async def _preflight(
        self,
        app: FastAPI,
        origin: str,
        method: str = "POST",
        headers: str = "authorization,content-type",
    ) -> httpx.Response:
        async with client_for(app) as client:
            return await client.options(
                "/api/scrape/start",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": headers,
                },
            )

    async def test_allowed_origin_preflight(self, database: Database) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        resp = await self._preflight(app, ALLOWED_ORIGIN)
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert "access-control-allow-credentials" not in resp.headers
        methods = {m.strip() for m in resp.headers["access-control-allow-methods"].split(",")}
        assert methods == {"GET", "POST", "OPTIONS"}
        allowed_headers = {
            h.strip().lower() for h in resp.headers["access-control-allow-headers"].split(",")
        }
        assert {"authorization", "content-type"} <= allowed_headers

    @pytest.mark.parametrize("origin", list(DEFAULT_CORS_ORIGINS))
    async def test_default_origins_are_allowed(self, database: Database, origin: str) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        resp = await self._preflight(app, origin)
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == origin

    async def test_disallowed_origin_preflight(self, database: Database) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        resp = await self._preflight(app, EVIL_ORIGIN)
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers
        assert "access-control-allow-credentials" not in resp.headers

    async def test_disallowed_method_preflight(self, database: Database) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        for method in ("DELETE", "PUT", "PATCH"):
            resp = await self._preflight(app, ALLOWED_ORIGIN, method=method)
            assert resp.status_code == 400

    async def test_disallowed_header_preflight(self, database: Database) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        resp = await self._preflight(app, ALLOWED_ORIGIN, headers="x-custom-header")
        assert resp.status_code == 400

    async def test_simple_request_headers(self, database: Database) -> None:
        app = make_app(database, api_auth_token=API_TOKEN)
        async with client_for(app) as client:
            ok = await client.get("/api/scrape/status", headers={"Origin": ALLOWED_ORIGIN})
            evil = await client.get("/api/scrape/status", headers={"Origin": EVIL_ORIGIN})
        assert ok.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert "access-control-allow-credentials" not in ok.headers
        assert "access-control-allow-origin" not in evil.headers

    async def test_origins_from_environment(
        self, database: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example/ ,")
        app = app_as_serve_builds_it(database)
        for origin in ("https://a.example", "https://b.example"):
            resp = await self._preflight(app, origin)
            assert resp.status_code == 200
            assert resp.headers["access-control-allow-origin"] == origin
        # Defaults are replaced, not extended
        assert (await self._preflight(app, ALLOWED_ORIGIN)).status_code == 400

    async def test_origins_env_fallback_when_settings_are_invalid(
        self, database: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_LEVEL", "bogus")
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example")
        app = app_as_serve_builds_it(database)
        assert (await self._preflight(app, "https://a.example")).status_code == 200
        assert (await self._preflight(app, ALLOWED_ORIGIN)).status_code == 400

    async def test_no_origins_handed_in_allows_none(self, database: Database) -> None:
        """The factory's own default is closed; serve hands it the configured list."""
        app = create_app(database, api_auth_token=API_TOKEN)
        for origin in DEFAULT_CORS_ORIGINS:
            assert (await self._preflight(app, origin)).status_code == 400

    async def test_invalid_origins_fail_closed(
        self, database: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CORS_ORIGINS", '["https://a.example"')  # truncated JSON
        app = app_as_serve_builds_it(database)
        assert (await self._preflight(app, ALLOWED_ORIGIN)).status_code == 400
        assert (await self._preflight(app, "https://a.example")).status_code == 400


class TestSettingsFields:
    """Parsing of API_AUTH_TOKEN and CORS_ORIGINS."""

    def test_defaults(self) -> None:
        settings = Settings(discord_bot_token="t", _env_file=None)
        assert settings.api_auth_token is None
        assert settings.cors_origins == [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8000",
            "https://connect.apehost.net",
        ]

    def test_default_origins_not_shared_between_instances(self) -> None:
        first = Settings(discord_bot_token="t", _env_file=None)
        first.cors_origins.append("https://mutated.example")
        second = Settings(discord_bot_token="t", _env_file=None)
        assert "https://mutated.example" not in second.cors_origins

    def test_token_is_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_AUTH_TOKEN", API_TOKEN)
        settings = Settings(discord_bot_token="t", _env_file=None)
        assert isinstance(settings.api_auth_token, SecretStr)
        assert settings.api_auth_token.get_secret_value() == API_TOKEN
        assert API_TOKEN not in repr(settings)

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_token_is_none(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("API_AUTH_TOKEN", raw)
        assert Settings(discord_bot_token="t", _env_file=None).api_auth_token is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("https://a.example", ["https://a.example"]),
            ("https://a.example,https://b.example", AB_ORIGINS),
            (" https://a.example , https://b.example/ ,,", AB_ORIGINS),
            ('["https://a.example", "https://b.example"]', AB_ORIGINS),
            ("", []),
        ],
    )
    def test_cors_origins_env_parsing(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
    ) -> None:
        monkeypatch.setenv("CORS_ORIGINS", raw)
        assert Settings(discord_bot_token="t", _env_file=None).cors_origins == expected

    def test_cors_origins_from_dotenv_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("CORS_ORIGINS=https://a.example,https://b.example\n")
        settings = Settings(discord_bot_token="t", _env_file=env_file)
        assert settings.cors_origins == ["https://a.example", "https://b.example"]

    @pytest.mark.parametrize("raw", ['["https://a.example"', "[1, 2]", '["a", {}]'])
    def test_invalid_cors_json_is_rejected(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("CORS_ORIGINS", raw)
        with pytest.raises(ValidationError):
            Settings(discord_bot_token="t", _env_file=None)


class TestNonLoopbackWarning:
    """The CLI warns when serving on a non-loopback interface."""

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "example.com"])
    def test_warns_for_exposed_hosts(self, host: str, capsys: pytest.CaptureFixture[str]) -> None:
        _warn_if_not_loopback(host)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "WARNING" in captured.err
        assert "API_AUTH_TOKEN" in captured.err

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "LOCALHOST", "::1", "[::1]"])
    def test_silent_for_loopback(self, host: str, capsys: pytest.CaptureFixture[str]) -> None:
        _warn_if_not_loopback(host)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
