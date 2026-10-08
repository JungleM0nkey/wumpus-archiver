"""Tests for CLI commands."""

from importlib.metadata import version as pkg_version
from pathlib import Path

import pytest
from click.testing import CliRunner

from wumpus_archiver.api.deps import wiring_of
from wumpus_archiver.cli import cli


class TestCLI:
    """Tests for CLI commands."""

    def test_cli_version(self) -> None:
        """Test --version flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert pkg_version("wumpus-archiver") in result.output

    def test_cli_help(self) -> None:
        """Test --help flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Wumpus Archiver" in result.output

    def test_scrape_missing_token(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test scrape command fails without token.

        A blank token fails ``Settings`` validation, so ``scrape`` stops before it
        builds a bot; a bot that is built anyway fails the test rather than reaching
        the network.
        """

        def no_bot(*args: object, **kwargs: object) -> None:
            pytest.fail("scrape built a bot despite a blank token")

        monkeypatch.setattr("wumpus_archiver.cli.ArchiverBot", no_bot)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["scrape", "--guild-id", "12345", "--output", str(tmp_path / "archive.db")],
            env={"DISCORD_BOT_TOKEN": ""},
        )
        assert result.exit_code != 0
        assert "Failed to load settings" in result.output
        assert "must not be empty" in result.output

    def test_scrape_missing_guild_id(self) -> None:
        """Test scrape command requires --guild-id."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["scrape"],
            env={"DISCORD_BOT_TOKEN": "test-token"},
        )
        assert result.exit_code != 0

    def test_scrape_invalid_output_dir(self, tmp_path) -> None:
        """Test scrape command rejects output path with nonexistent parent."""
        runner = CliRunner()
        bad_path = tmp_path / "nonexistent" / "deep" / "archive.db"
        result = runner.invoke(
            cli,
            ["scrape", "--guild-id", "12345", "--output", str(bad_path)],
            env={"DISCORD_BOT_TOKEN": "test-token"},
        )
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_serve_composes_app_and_hands_it_to_uvicorn(self, tmp_path, monkeypatch) -> None:
        """serve builds the app from the CLI's inputs and runs it with the given host/port."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        attachments = tmp_path / "attachments"
        attachments.mkdir()
        # serve resolves the bot token from the environment and .env; pin both to "none".
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        # serve discovers the portal build on disk; pin it to a fake one.
        build = tmp_path / "build"
        build.mkdir()
        (build / "index.html").write_text("<!doctype html>")
        monkeypatch.setattr("wumpus_archiver.compose.portal_build_dir", lambda: build)

        calls: list[tuple[object, dict[str, object]]] = []

        def fake_run(app: object, **kwargs: object) -> None:
            calls.append((app, kwargs))

        monkeypatch.setattr("uvicorn.run", fake_run)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["serve", str(db_file), "--host", "0.0.0.0", "--port", "9999", "-a", str(attachments)],
        )

        assert result.exit_code == 0, result.output
        assert len(calls) == 1
        app, kwargs = calls[0]
        assert kwargs == {"host": "0.0.0.0", "port": 9999}
        wiring = wiring_of(app)
        assert wiring.database.database_url == f"sqlite+aiosqlite:///{db_file.resolve()}"
        assert wiring.database.connected is False, "the app's lifespan owns the connection"
        assert wiring.attachments_dir == attachments.resolve()
        assert wiring.portal_build == build.resolve()
        assert f"Portal: {build}" in result.output
        assert wiring.scrape.configured is False
        assert "Scrape control: read-only" in result.output

    def test_serve_without_attachments_dir(self, tmp_path, monkeypatch) -> None:
        """A missing attachments directory means images are served from the CDN."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.setattr("wumpus_archiver.compose.portal_build_dir", lambda: None)
        apps: list[object] = []
        monkeypatch.setattr("uvicorn.run", lambda app, **kw: apps.append(app))

        result = CliRunner().invoke(cli, ["serve", str(db_file), "-a", str(tmp_path / "nope")])

        assert result.exit_code == 0, result.output
        assert "images served from Discord CDN" in result.output
        assert "Portal: not built" in result.output
        assert wiring_of(apps[0]).attachments_dir is None
        assert wiring_of(apps[0]).portal_build is None

    def test_serve_enables_scrape_control_with_a_token(self, tmp_path, monkeypatch) -> None:
        """A bot token in the environment turns scrape control on without starting anything."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "a-real-looking-token")
        monkeypatch.setattr("wumpus_archiver.compose.portal_build_dir", lambda: None)
        apps: list[object] = []
        monkeypatch.setattr("uvicorn.run", lambda app, **kw: apps.append(app))

        result = CliRunner().invoke(cli, ["serve", str(db_file)])

        assert result.exit_code == 0, result.output
        assert "Scrape control: enabled" in result.output
        assert wiring_of(apps[0]).scrape.configured is True

    def test_serve_reports_invalid_settings_instead_of_going_read_only(
        self, tmp_path, monkeypatch
    ) -> None:
        """A bad setting next to a valid token is an error, not silently read-only."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "a-real-looking-token")
        monkeypatch.setenv("API_PORT", "70000")
        monkeypatch.setattr("wumpus_archiver.compose.portal_build_dir", lambda: None)
        monkeypatch.setattr("uvicorn.run", lambda app, **kw: pytest.fail("uvicorn must not run"))

        result = CliRunner().invoke(cli, ["serve", str(db_file)])

        assert result.exit_code == 1
        assert "Failed to load settings" in result.output
        assert "Port must be between" in result.output

    def test_serve_reports_invalid_settings_before_building_the_portal(
        self, tmp_path, monkeypatch
    ) -> None:
        db_file = tmp_path / "test.db"
        db_file.touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("API_PORT", "70000")
        monkeypatch.setattr(
            "wumpus_archiver.cli._build_portal_static",
            lambda: pytest.fail("the portal must not be built over invalid settings"),
        )

        result = CliRunner().invoke(cli, ["serve", "--build-portal", str(db_file)])

        assert result.exit_code == 1
        assert "Failed to load settings" in result.output

    def test_serve_starts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test serve command starts the portal."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        calls: list[tuple[object, str, int]] = []

        def fake_run(app: object, host: str, port: int, **kwargs: object) -> None:
            calls.append((app, host, port))

        # `serve` does `import uvicorn` at call time, so patching the module attribute
        # keeps the test from binding a real port and blocking forever.
        monkeypatch.setattr("uvicorn.run", fake_run)
        runner = CliRunner()
        result = runner.invoke(cli, ["serve", str(db_file)])
        assert result.exit_code == 0
        assert len(calls) == 1
        _, host, port = calls[0]
        assert (host, port) == ("127.0.0.1", 8000)
        # Should not report 'not yet implemented'
        assert "not yet implemented" not in (result.output or "")

    @pytest.mark.parametrize("kind", ["file", "missing"])
    def test_dev_passes_no_attachments_dir_unless_it_is_a_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
    ) -> None:
        """Like serve, dev never hands the factory a path that is not a directory."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        attachments = tmp_path / "attachments"
        if kind == "file":
            attachments.write_text("not a directory")
        portal = tmp_path / "portal"
        (portal / "node_modules").mkdir(parents=True)
        written: list[Path | None] = []

        async def no_processes(*args: object, **kwargs: object) -> int:
            return 0

        monkeypatch.setattr("wumpus_archiver.utils.process_manager.find_npm", lambda: "npm")
        monkeypatch.setattr(
            "wumpus_archiver.utils.process_manager.resolve_portal_dir", lambda: portal
        )
        monkeypatch.setattr("wumpus_archiver.utils.process_manager.run_concurrently", no_processes)
        monkeypatch.setattr(
            "wumpus_archiver.cli._write_dev_app_module", lambda db, att: written.append(att)
        )

        result = CliRunner().invoke(cli, ["dev", str(db_file), "-a", str(attachments)])

        assert result.exit_code == 0, result.output
        assert written == [None]

    def test_update_not_implemented(self, tmp_path) -> None:
        """Test update command returns error (not implemented)."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["update", str(db_file), "--guild-id", "12345"],
        )
        assert result.exit_code == 2
        assert "not yet implemented" in result.output

    def test_init_creates_structure(self, tmp_path) -> None:
        """Test init command creates project structure."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert Path(".env").exists()
            assert Path("attachments").is_dir()
            assert Path("logs").is_dir()

    def test_init_preserves_existing_env(self, tmp_path) -> None:
        """Test init doesn't overwrite existing .env."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path(".env").write_text("MY_CUSTOM=stuff\n")
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert ".env file already exists" in result.output
            assert Path(".env").read_text() == "MY_CUSTOM=stuff\n"

    def test_init_idempotent(self, tmp_path) -> None:
        """Test init can be run multiple times safely."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result1 = runner.invoke(cli, ["init"])
            result2 = runner.invoke(cli, ["init"])
            assert result1.exit_code == 0
            assert result2.exit_code == 0
