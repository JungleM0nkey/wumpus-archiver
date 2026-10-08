"""The composition helpers that ``serve`` and the dev module share."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from wumpus_archiver import compose
from wumpus_archiver.api.scrape_control import ReadOnlyScrape
from wumpus_archiver.api.scrape_manager import ScrapeJobManager
from wumpus_archiver.config import DEFAULT_CORS_ORIGINS, Settings
from wumpus_archiver.storage.database import Database


def _build(root: Path) -> Path:
    """A built portal under ``root``: ``portal/build/index.html`` and nothing else."""
    build = root / "portal" / "build"
    build.mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html>")
    return build


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty fake checkout for the source-tree lookup and an empty working directory."""
    fake_module = tmp_path / "checkout" / "src" / "wumpus_archiver" / "compose.py"
    monkeypatch.setattr(compose, "__file__", str(fake_module))
    (tmp_path / "cwd").mkdir()
    monkeypatch.chdir(tmp_path / "cwd")
    return tmp_path


class TestPortalBuildDir:
    def test_a_build_without_the_portal_sources_is_served(self, roots: Path) -> None:
        """A deployment that ships only ``portal/build`` (no package.json) still gets the UI."""
        build = _build(roots / "cwd")
        assert not (build.parent / "package.json").exists()
        found = compose.portal_build_dir()
        assert found is not None and found.resolve() == build.resolve()

    def test_the_source_tree_build_comes_first(self, roots: Path) -> None:
        source = _build(roots / "checkout")
        _build(roots / "cwd")
        found = compose.portal_build_dir()
        assert found is not None and found.resolve() == source.resolve()

    def test_none_without_a_built_index(self, roots: Path) -> None:
        (roots / "cwd" / "portal" / "build").mkdir(parents=True)
        assert compose.portal_build_dir() is None


@pytest.fixture
def clean_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty working directory (no ``.env``) and none of the settings this reads."""
    for var in ("DISCORD_BOT_TOKEN", "API_AUTH_TOKEN", "CORS_ORIGINS", "API_PORT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _revealed(secret: SecretStr | None) -> str | None:
    return secret.get_secret_value() if secret is not None else None


class TestServeConfig:
    """``serve_config`` is how composition roots read the bot token, API token and origins."""

    def test_reads_all_three_from_the_environment(
        self, clean_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
        monkeypatch.setenv("API_AUTH_TOKEN", "api-token")
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example")
        config = compose.serve_config()
        assert _revealed(config.bot_token) == "env-token"
        assert _revealed(config.api_auth_token) == "api-token"
        assert config.cors_origins == ("https://a.example",)

    def test_reads_dot_env_in_the_working_directory(self, clean_env: Path) -> None:
        (clean_env / ".env").write_text(
            "DISCORD_BOT_TOKEN=file-token\nAPI_AUTH_TOKEN=file-api-token\n"
        )
        config = compose.serve_config()
        assert _revealed(config.bot_token) == "file-token"
        assert _revealed(config.api_auth_token) == "file-api-token"

    def test_defaults_when_unset(self, clean_env: Path) -> None:
        config = compose.serve_config()
        assert config.bot_token is None
        assert config.api_auth_token is None
        assert config.cors_origins == DEFAULT_CORS_ORIGINS

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_tokens_are_none(
        self, clean_env: Path, monkeypatch: pytest.MonkeyPatch, blank: str
    ) -> None:
        monkeypatch.setenv("DISCORD_BOT_TOKEN", blank)
        monkeypatch.setenv("API_AUTH_TOKEN", blank)
        config = compose.serve_config()
        assert config.bot_token is None
        assert config.api_auth_token is None

    def test_bot_token_is_the_one_settings_reads(
        self, clean_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``serve`` and ``scrape`` must hand Discord the same credential, padding and all."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", " padded-token ")
        expected = Settings().discord_bot_token.get_secret_value()  # type: ignore[call-arg]
        assert _revealed(compose.serve_config().bot_token) == expected == " padded-token "

    def test_api_token_is_stripped(self, clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_AUTH_TOKEN", " api-token ")
        assert _revealed(compose.serve_config().api_auth_token) == "api-token"

    def test_tokens_never_show_in_a_repr(
        self, clean_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
        monkeypatch.setenv("API_AUTH_TOKEN", "api-token")
        text = repr(compose.serve_config())
        assert "env-token" not in text
        assert "api-token" not in text

    @pytest.mark.parametrize("bot_token", ["env-token", "", None])
    def test_unrelated_invalid_settings_raise(
        self, clean_env: Path, monkeypatch: pytest.MonkeyPatch, bot_token: str | None
    ) -> None:
        """A bad API_PORT is a misconfiguration, whatever the bot token, not read-only mode."""
        if bot_token is not None:
            monkeypatch.setenv("DISCORD_BOT_TOKEN", bot_token)
        monkeypatch.setenv("API_PORT", "70000")
        with pytest.raises(ValidationError, match="Port must be between"):
            compose.serve_config()

    def test_unparseable_origins_raise(
        self, clean_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CORS_ORIGINS", '["https://a.example"')  # truncated JSON
        with pytest.raises(ValidationError, match="CORS_ORIGINS"):
            compose.serve_config()


class TestScrapeControl:
    def test_read_only_without_a_bot_token(self) -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        assert isinstance(compose.scrape_control(database, None), ReadOnlyScrape)

    def test_enabled_with_a_bot_token(self) -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        scrape = compose.scrape_control(database, SecretStr("bot-token"))
        assert isinstance(scrape, ScrapeJobManager)
        assert scrape._token == "bot-token"
