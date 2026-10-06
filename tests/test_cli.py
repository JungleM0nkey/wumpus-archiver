"""Tests for CLI commands."""

from importlib.metadata import version as pkg_version
from pathlib import Path

from click.testing import CliRunner

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

    def test_scrape_missing_token(self) -> None:
        """Test scrape command fails without token."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["scrape", "--guild-id", "12345"],
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
        # The factory still reads Settings()/.env when no token is given; keep the
        # test hermetic until create_app stops doing so.
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

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
        assert app.state.database.database_url == f"sqlite+aiosqlite:///{db_file.resolve()}"
        assert app.state.attachments_path == attachments.resolve()
        assert app.state.discord_token is None

    def test_serve_without_attachments_dir(self, tmp_path, monkeypatch) -> None:
        """A missing attachments directory means images are served from the CDN."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        apps: list[object] = []
        monkeypatch.setattr("uvicorn.run", lambda app, **kw: apps.append(app))

        result = CliRunner().invoke(cli, ["serve", str(db_file), "-a", str(tmp_path / "nope")])

        assert result.exit_code == 0, result.output
        assert "images served from Discord CDN" in result.output
        assert apps[0].state.attachments_path is None

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
