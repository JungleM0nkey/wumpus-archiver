"""Tests for the mirror/backfill CLI wiring of SecretStr bridge settings."""

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from wumpus_archiver import cli as cli_module
from wumpus_archiver.bot import backfill as backfill_module
from wumpus_archiver.bot import mirror as mirror_module
from wumpus_archiver.cli import cli

FAKE_DISCORD_TOKEN = "fake-discord-token-AAAA1111"
FAKE_BRIDGE_TOKEN = "fake-bridge-token-BBBB2222"
FAKE_CF_ID = "fake-cf-id-DDDD4444"
FAKE_CF_SECRET = "fake-cf-secret-CCCC3333"
BRIDGE_URL = "https://bridge.example.test/chat/bridge"

ENV_VARS = (
    "DISCORD_BOT_TOKEN",
    "GUILD_ID",
    "CHAT_BRIDGE_URL",
    "CHAT_BRIDGE_TOKEN",
    "CF_ACCESS_CLIENT_ID",
    "CF_ACCESS_CLIENT_SECRET",
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

    def test_insecure_bridge_url_is_rejected(self) -> None:
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
        assert "must use https" in result.output
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


class TestScrapeCommandToken:
    """The scrape command hands the bot a plain-str token."""

    def test_passes_plain_string_token(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test ArchiverBot receives the unwrapped token string."""
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

        result = CliRunner().invoke(
            cli,
            ["scrape", "--guild-id", "12345", "--output", str(tmp_path / "out.db")],
            env={"DISCORD_BOT_TOKEN": FAKE_DISCORD_TOKEN},
        )
        assert result.exit_code == 0, result.output
        assert type(captured["token"]) is str
        assert captured["token"] == FAKE_DISCORD_TOKEN
        assert FAKE_DISCORD_TOKEN not in result.output
