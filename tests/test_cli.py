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

    def test_serve_starts(self, tmp_path) -> None:
        """Test serve command starts the portal."""
        db_file = tmp_path / "test.db"
        db_file.touch()
        runner = CliRunner()
        # Serve will try to start uvicorn — catch the SystemExit or verify
        # it gets past validation and into the startup path.
        result = runner.invoke(cli, ["serve", str(db_file)])
        # Should not report 'not yet implemented'
        assert "not yet implemented" not in (result.output or "")

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
