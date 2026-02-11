"""Tests for configuration management."""

import pytest
from pydantic import ValidationError

from wumpus_archiver.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_defaults(self) -> None:
        """Test default values are set correctly."""
        settings = Settings(discord_bot_token="test-token", _env_file=None)
        assert settings.api_host == "127.0.0.1"
        assert settings.api_port == 8000
        assert settings.api_debug is False
        assert settings.batch_size == 1000
        assert settings.rate_limit_delay == 0.5
        assert settings.max_retries == 5
        assert settings.download_attachments is True
        assert settings.default_page_size == 50
        assert settings.log_level == "INFO"
        assert settings.log_file is None

    def test_token_required(self) -> None:
        """Test that discord_bot_token is required."""
        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    def test_port_validation_low(self) -> None:
        """Test port validation rejects 0."""
        with pytest.raises(ValueError, match="Port must be between"):
            Settings(discord_bot_token="t", api_port=0, _env_file=None)

    def test_port_validation_high(self) -> None:
        """Test port validation rejects >65535."""
        with pytest.raises(ValueError, match="Port must be between"):
            Settings(discord_bot_token="t", api_port=70000, _env_file=None)

    def test_batch_size_validation(self) -> None:
        """Test batch size validation rejects 0."""
        with pytest.raises(ValueError, match="Batch size must be positive"):
            Settings(discord_bot_token="t", batch_size=0, _env_file=None)

    def test_page_size_validation_low(self) -> None:
        """Test page size validation rejects 0."""
        with pytest.raises(ValueError, match="Page size must be between"):
            Settings(discord_bot_token="t", default_page_size=0, _env_file=None)

    def test_page_size_validation_high(self) -> None:
        """Test page size validation rejects >1000."""
        with pytest.raises(ValueError, match="Page size must be between"):
            Settings(discord_bot_token="t", default_page_size=5000, _env_file=None)

    def test_rate_limit_delay_validation(self) -> None:
        """Test rate limit delay rejects negative."""
        with pytest.raises(ValueError, match="non-negative"):
            Settings(discord_bot_token="t", rate_limit_delay=-1.0, _env_file=None)

    def test_max_retries_validation(self) -> None:
        """Test max retries rejects negative."""
        with pytest.raises(ValueError, match="non-negative"):
            Settings(discord_bot_token="t", max_retries=-1, _env_file=None)

    def test_log_level_validation(self) -> None:
        """Test log level rejects invalid values."""
        with pytest.raises(ValueError, match="Log level must be one of"):
            Settings(discord_bot_token="t", log_level="TRACE", _env_file=None)

    def test_log_level_case_insensitive(self) -> None:
        """Test log level is normalized to uppercase."""
        settings = Settings(discord_bot_token="t", log_level="debug", _env_file=None)
        assert settings.log_level == "DEBUG"

    def test_valid_custom_settings(self) -> None:
        """Test creating settings with all custom values."""
        settings = Settings(
            discord_bot_token="my-token",
            api_port=3000,
            batch_size=500,
            default_page_size=25,
            rate_limit_delay=1.0,
            max_retries=3,
            log_level="WARNING",
            _env_file=None,
        )
        assert settings.api_port == 3000
        assert settings.batch_size == 500
        assert settings.default_page_size == 25

    def test_env_var_alias(self, monkeypatch) -> None:
        """Test that environment variable aliases work."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
        monkeypatch.setenv("API_PORT", "9999")
        settings = Settings(_env_file=None)
        assert settings.discord_bot_token == "env-token"
        assert settings.api_port == 9999
