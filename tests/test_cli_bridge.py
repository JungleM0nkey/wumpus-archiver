"""Tests for the mirror/backfill CLI wiring of SecretStr bridge settings."""

from pathlib import Path
from typing import Any

import httpx
import pytest
from click.testing import CliRunner

from wumpus_archiver import cli as cli_module
from wumpus_archiver.api.app import create_app
from wumpus_archiver.api.deps import wiring_of
from wumpus_archiver.api.scrape_manager import ScrapeJobManager
from wumpus_archiver.bot import backfill as backfill_module
from wumpus_archiver.bot import mirror as mirror_module
from wumpus_archiver.cli import cli
from wumpus_archiver.compose import scrape_control, serve_config
from wumpus_archiver.config import DEFAULT_CHAT_BRIDGE_URL
from wumpus_archiver.storage.database import Database

FAKE_DISCORD_TOKEN = "fake-discord-token-AAAA1111"
FAKE_BRIDGE_TOKEN = "fake-bridge-token-BBBB2222"
FAKE_CF_ID = "fake-cf-id-DDDD4444"
FAKE_CF_SECRET = "fake-cf-secret-CCCC3333"
FAKE_URL_PASSWORD = "fake-url-pass-EEEE5555"
FAKE_API_TOKEN = "fake-api-token-FFFF6666"
BRIDGE_URL = "https://bridge.example.test/chat/bridge"

ENV_VARS = (
    "DISCORD_BOT_TOKEN",
    "GUILD_ID",
    "CHAT_BRIDGE_URL",
    "CHAT_BRIDGE_TOKEN",
    "CF_ACCESS_CLIENT_ID",
    "CF_ACCESS_CLIENT_SECRET",
    "API_AUTH_TOKEN",
    "CORS_ORIGINS",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run in an empty directory (no .env) with no bridge-related variables set."""
    monkeypatch.chdir(tmp_path)
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


class FakeBridge:
    """Stand-in for BridgeClient that records its constructor arguments."""

    instances: list["FakeBridge"] = []

    def __init__(self, *args: Any) -> None:
        self.args = args
        FakeBridge.instances.append(self)

    async def __aenter__(self) -> "FakeBridge":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def fake_bridge(monkeypatch: pytest.MonkeyPatch) -> type[FakeBridge]:
    """Replace BridgeClient with a recording fake."""
    FakeBridge.instances = []
    monkeypatch.setattr(mirror_module, "BridgeClient", FakeBridge)
    return FakeBridge


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    """An existing (empty) database file for the backfill argument."""
    path = tmp_path / "archive.db"
    path.touch()
    return path


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch, fake_bridge: type[FakeBridge]) -> list[str]:
    """Replace the mirror bot and backfill runner so nothing ever reaches Discord or a bridge.

    The returned list records "mirror"/"backfill" whenever a command gets as far as starting
    work, so a test can assert a rejected URL aborted before that point.
    """
    calls: list[str] = []

    class FakeMirrorBot:
        def __init__(self, token: Any, guild_id: int, bridge: Any) -> None:
            self.bridge = bridge

        def run_sync(self) -> None:
            calls.append("mirror")

    async def fake_run_backfill(*args: Any) -> int:
        calls.append("backfill")
        return 0

    monkeypatch.setattr(mirror_module, "MirrorBot", FakeMirrorBot)
    monkeypatch.setattr(backfill_module, "run_backfill", fake_run_backfill)
    return calls


def _bridge_command(command: str, db_file: Path) -> list[str]:
    """CLI arguments for the mirror or backfill command."""
    if command == "mirror":
        return ["mirror", "--guild-id", "12345"]
    return ["backfill", str(db_file), "--guild-id", "12345"]


class TestMirrorCommand:
    """The mirror command reads SecretStr settings only at the point of use."""

    def test_missing_bridge_token_exits(self) -> None:
        """Test an unset (empty) CHAT_BRIDGE_TOKEN is reported and aborts."""
        result = CliRunner().invoke(
            cli,
            ["mirror", "--guild-id", "12345"],
            env={"DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN},
        )
        assert result.exit_code == 1
        assert "CHAT_BRIDGE_TOKEN is required" in result.output
        assert FAKE_DISCORD_TOKEN not in result.output

    def test_empty_bridge_token_exits(self) -> None:
        """Test an explicitly empty CHAT_BRIDGE_TOKEN is treated as unset."""
        result = CliRunner().invoke(
            cli,
            ["mirror", "--guild-id", "12345"],
            env={"DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN, "CHAT_BRIDGE_TOKEN": ""},
        )
        assert result.exit_code == 1
        assert "CHAT_BRIDGE_TOKEN is required" in result.output

    def test_insecure_bridge_url_is_rejected(self, started: list[str]) -> None:
        """Test an http:// remote bridge URL aborts before any secret is used."""
        result = CliRunner().invoke(
            cli,
            ["mirror", "--guild-id", "12345"],
            env={
                "DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN,
                "CHAT_BRIDGE_URL": "http://bridge.example.test/chat/bridge",
                "CHAT_BRIDGE_TOKEN": FAKE_BRIDGE_TOKEN,
                "CF_ACCESS_CLIENT_SECRET": FAKE_CF_SECRET,
            },
        )
        assert result.exit_code == 1
        assert "CHAT_BRIDGE_URL must use https" in result.output
        # Rejected by the command itself, not by Settings failing to load
        assert "Failed to load settings" not in result.output
        assert started == []
        for secret in (FAKE_DISCORD_TOKEN, FAKE_BRIDGE_TOKEN, FAKE_CF_SECRET):
            assert secret not in result.output

    def test_passes_plain_strings_to_clients(
        self, monkeypatch: pytest.MonkeyPatch, fake_bridge: type[FakeBridge]
    ) -> None:
        """Test secrets are unwrapped into plain str when wiring bot and bridge."""
        captured: dict[str, Any] = {}

        class FakeMirrorBot:
            def __init__(self, token: Any, guild_id: int, bridge: Any) -> None:
                captured.update(token=token, guild_id=guild_id, bridge=bridge)

            def run_sync(self) -> None:
                captured["ran"] = True

        monkeypatch.setattr(mirror_module, "MirrorBot", FakeMirrorBot)

        result = CliRunner().invoke(
            cli,
            ["mirror", "--guild-id", "12345"],
            env={
                "DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN,
                "CHAT_BRIDGE_URL": BRIDGE_URL,
                "CHAT_BRIDGE_TOKEN": FAKE_BRIDGE_TOKEN,
                "CF_ACCESS_CLIENT_ID": FAKE_CF_ID,
                "CF_ACCESS_CLIENT_SECRET": FAKE_CF_SECRET,
            },
        )
        assert result.exit_code == 0, result.output
        assert captured["ran"] is True
        assert captured["guild_id"] == 12345
        assert type(captured["token"]) is str
        assert captured["token"] == FAKE_DISCORD_TOKEN
        assert fake_bridge.instances[0].args == (
            BRIDGE_URL,
            FAKE_BRIDGE_TOKEN,
            FAKE_CF_ID,
            FAKE_CF_SECRET,
        )
        assert all(type(arg) is str for arg in fake_bridge.instances[0].args)
        for secret in (FAKE_DISCORD_TOKEN, FAKE_BRIDGE_TOKEN, FAKE_CF_SECRET):
            assert secret not in result.output


class TestBackfillCommand:
    """The backfill command reads SecretStr settings only at the point of use."""

    def test_missing_bridge_token_exits(self, db_file: Path) -> None:
        """Test an unset (empty) CHAT_BRIDGE_TOKEN is reported and aborts."""
        result = CliRunner().invoke(
            cli,
            ["backfill", str(db_file), "--guild-id", "12345"],
            env={"DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN},
        )
        assert result.exit_code == 1
        assert "CHAT_BRIDGE_TOKEN is required" in result.output

    def test_passes_plain_strings_to_bridge(
        self, monkeypatch: pytest.MonkeyPatch, fake_bridge: type[FakeBridge], db_file: Path
    ) -> None:
        """Test secrets are unwrapped into plain str when building the BridgeClient."""
        calls: list[tuple[Any, ...]] = []

        async def fake_run_backfill(*args: Any) -> int:
            calls.append(args)
            return 0

        monkeypatch.setattr(backfill_module, "run_backfill", fake_run_backfill)

        result = CliRunner().invoke(
            cli,
            ["backfill", str(db_file), "--guild-id", "12345"],
            env={
                "DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN,
                "CHAT_BRIDGE_URL": BRIDGE_URL,
                "CHAT_BRIDGE_TOKEN": FAKE_BRIDGE_TOKEN,
                "CF_ACCESS_CLIENT_ID": FAKE_CF_ID,
                "CF_ACCESS_CLIENT_SECRET": FAKE_CF_SECRET,
            },
        )
        assert result.exit_code == 0, result.output
        assert len(calls) == 1
        assert fake_bridge.instances[0].args == (
            BRIDGE_URL,
            FAKE_BRIDGE_TOKEN,
            FAKE_CF_ID,
            FAKE_CF_SECRET,
        )
        assert all(type(arg) is str for arg in fake_bridge.instances[0].args)
        for secret in (FAKE_DISCORD_TOKEN, FAKE_BRIDGE_TOKEN, FAKE_CF_SECRET):
            assert secret not in result.output


class TestBridgeUrlValidation:
    """mirror and backfill validate CHAT_BRIDGE_URL where the bridge secrets are about to be used."""

    @pytest.mark.parametrize("command", ["mirror", "backfill"])
    @pytest.mark.parametrize(
        ("bridge_url", "expected"),
        [
            ("http://bridge.example.test/chat/bridge", "CHAT_BRIDGE_URL must use https"),
            ("ftp://bridge.example.test/chat/bridge", "CHAT_BRIDGE_URL must use https"),
            (
                f"https://user:{FAKE_URL_PASSWORD}@bridge.example.test/chat/bridge",
                "CHAT_BRIDGE_URL must not contain credentials",
            ),
            (
                f"http://user:{FAKE_URL_PASSWORD}@localhost:8787/chat/bridge",
                "CHAT_BRIDGE_URL must not contain credentials",
            ),
            (
                "https://bridge.example.test:99999/chat/bridge",
                "CHAT_BRIDGE_URL has an invalid port",
            ),
        ],
    )
    def test_bad_bridge_url_aborts_cleanly(
        self,
        command: str,
        bridge_url: str,
        expected: str,
        db_file: Path,
        started: list[str],
        fake_bridge: type[FakeBridge],
    ) -> None:
        """Test a bad URL exits 1 with a clean message, before any client or work starts."""
        result = CliRunner().invoke(
            cli,
            _bridge_command(command, db_file),
            env={
                "DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN,
                "CHAT_BRIDGE_URL": bridge_url,
                "CHAT_BRIDGE_TOKEN": FAKE_BRIDGE_TOKEN,
                "CF_ACCESS_CLIENT_ID": FAKE_CF_ID,
                "CF_ACCESS_CLIENT_SECRET": FAKE_CF_SECRET,
            },
        )
        assert result.exit_code == 1, result.output
        assert expected in result.output
        # Rejected by the command itself, not by Settings failing to load
        assert "Failed to load settings" not in result.output
        assert started == []
        assert fake_bridge.instances == []
        # Nothing secret (and not the URL, which may embed credentials) is printed
        for secret in (
            FAKE_DISCORD_TOKEN,
            FAKE_BRIDGE_TOKEN,
            FAKE_CF_ID,
            FAKE_CF_SECRET,
            FAKE_URL_PASSWORD,
            "bridge.example.test",
        ):
            assert secret not in result.output

    @pytest.mark.parametrize("command", ["mirror", "backfill"])
    def test_blank_bridge_url_uses_default(
        self, command: str, db_file: Path, started: list[str], fake_bridge: type[FakeBridge]
    ) -> None:
        """Test a blank CHAT_BRIDGE_URL falls back to the default (https) URL."""
        result = CliRunner().invoke(
            cli,
            _bridge_command(command, db_file),
            env={
                "DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN,
                "CHAT_BRIDGE_URL": "  ",
                "CHAT_BRIDGE_TOKEN": FAKE_BRIDGE_TOKEN,
            },
        )
        assert result.exit_code == 0, result.output
        assert started == [command]
        assert fake_bridge.instances[0].args[0] == DEFAULT_CHAT_BRIDGE_URL

    @pytest.mark.parametrize("command", ["mirror", "backfill"])
    def test_loopback_http_bridge_url_is_allowed(
        self, command: str, db_file: Path, started: list[str], fake_bridge: type[FakeBridge]
    ) -> None:
        """Test plain http to a loopback host (local development) still works."""
        result = CliRunner().invoke(
            cli,
            _bridge_command(command, db_file),
            env={
                "DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN,
                "CHAT_BRIDGE_URL": "http://127.0.0.1:8787/bridge",
                "CHAT_BRIDGE_TOKEN": FAKE_BRIDGE_TOKEN,
            },
        )
        assert result.exit_code == 0, result.output
        assert started == [command]
        assert fake_bridge.instances[0].args[0] == "http://127.0.0.1:8787/bridge"


@pytest.fixture
def fake_scrape_bot(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ArchiverBot with a fake that records the token it was given."""
    captured: dict[str, Any] = {}

    class FakeBot:
        def __init__(self, token: Any, database: Any) -> None:
            captured["token"] = token

        async def start(self) -> None:
            return None

        async def scrape_guild(self, guild_id: int, progress: Any) -> dict[str, Any]:
            return {
                "guild_name": "g",
                "channels_scraped": 0,
                "messages_scraped": 0,
                "attachments_found": 0,
                "errors": [],
            }

        async def close(self) -> None:
            return None

    monkeypatch.setattr(cli_module, "ArchiverBot", FakeBot)
    return captured


class TestScrapeCommandToken:
    """The scrape command hands the bot a plain-str token."""

    def test_passes_plain_string_token(
        self, fake_scrape_bot: dict[str, Any], tmp_path: Path
    ) -> None:
        """Test ArchiverBot receives the unwrapped token string."""
        result = CliRunner().invoke(
            cli,
            ["scrape", "--guild-id", "12345", "--output", str(tmp_path / "out.db")],
            env={"DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN},
        )
        assert result.exit_code == 0, result.output
        assert type(fake_scrape_bot["token"]) is str
        assert fake_scrape_bot["token"] == FAKE_DISCORD_TOKEN
        assert FAKE_DISCORD_TOKEN not in result.output


# Values that the bridge commands reject but that must not affect anything else
UNUSABLE_BRIDGE_URLS = [
    "",
    "   ",
    "http://bridge.example.test/chat/bridge",
    f"https://user:{FAKE_URL_PASSWORD}@bridge.example.test/chat/bridge",
    "https://bridge.example.test:99999/chat/bridge",
]


class TestBridgeUrlDoesNotAffectOtherCommands:
    """A blank or unusable CHAT_BRIDGE_URL only matters to mirror/backfill, not to Settings."""

    @pytest.mark.parametrize("bridge_url", UNUSABLE_BRIDGE_URLS)
    def test_scrape_still_runs(
        self, bridge_url: str, fake_scrape_bot: dict[str, Any], tmp_path: Path
    ) -> None:
        """Test ``scrape`` loads its settings and token despite the bridge URL value."""
        result = CliRunner().invoke(
            cli,
            ["scrape", "--guild-id", "12345", "--output", str(tmp_path / "out.db")],
            env={"DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN, "CHAT_BRIDGE_URL": bridge_url},
        )
        assert result.exit_code == 0, result.output
        assert "Failed to load settings" not in result.output
        assert fake_scrape_bot["token"] == FAKE_DISCORD_TOKEN
        assert FAKE_URL_PASSWORD not in result.output

    @pytest.mark.parametrize("bridge_url", UNUSABLE_BRIDGE_URLS)
    async def test_the_app_still_gets_its_dotenv_settings(
        self,
        bridge_url: str,
        database: Database,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test the app serve composes keeps the .env bot token, API token and CORS origins.

        A failing Settings() used to silently turn scrape control off and reset CORS to the
        defaults, because the .env values are only visible through Settings. The app is
        built the way ``serve`` builds it: the compose helpers read the settings and
        ``create_app`` is handed the values.
        """
        origin = "https://portal.example.test"
        (tmp_path / ".env").write_text(
            f"DISCORD_BOT_TOKEN={FAKE_DISCORD_TOKEN}\n"
            f"API_AUTH_TOKEN={FAKE_API_TOKEN}\n"
            f"CORS_ORIGINS={origin}\n"
            f"CHAT_BRIDGE_URL={bridge_url}\n",
            encoding="utf-8",
        )

        with caplog.at_level("INFO"):
            config = serve_config()
            scrape = scrape_control(database, config.bot_token)
            app = create_app(
                database,
                scrape=scrape,
                api_auth_token=config.api_auth_token,
                cors_origins=config.cors_origins,
            )

        assert isinstance(scrape, ScrapeJobManager)
        assert scrape._token == FAKE_DISCORD_TOKEN
        wired_token = wiring_of(app).api_auth_token
        assert wired_token is not None and wired_token.get_secret_value() == FAKE_API_TOKEN
        assert "read-only" not in caplog.text
        assert FAKE_URL_PASSWORD not in caplog.text

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            allowed = await client.options(
                "/api/scrape/start",
                headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
            )
            denied = await client.options(
                "/api/scrape/start",
                headers={
                    "Origin": "http://localhost:5173",  # a default origin, replaced by CORS_ORIGINS
                    "Access-Control-Request-Method": "POST",
                },
            )
        assert allowed.headers.get("access-control-allow-origin") == origin
        assert "access-control-allow-origin" not in denied.headers
