"""Tests for configuration management."""

import pytest
from pydantic import SecretStr, ValidationError

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
        assert settings.discord_bot_token.get_secret_value() == "env-token"
        assert settings.api_port == 9999


FAKE_DISCORD_TOKEN = "fake-discord-token-AAAA1111"
FAKE_BRIDGE_TOKEN = "fake-bridge-token-BBBB2222"
FAKE_CF_SECRET = "fake-cf-secret-CCCC3333"

SECRET_ENV_VARS = (
    "DISCORD_BOT_TOKEN",
    "CHAT_BRIDGE_URL",
    "CHAT_BRIDGE_TOKEN",
    "CF_ACCESS_CLIENT_ID",
    "CF_ACCESS_CLIENT_SECRET",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove secret-related variables so the host environment cannot leak in."""
    for name in SECRET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _secret_settings(**overrides: str) -> Settings:
    """Build Settings with fake values for every secret field."""
    values = {
        "discord_bot_token": FAKE_DISCORD_TOKEN,
        "chat_bridge_token": FAKE_BRIDGE_TOKEN,
        "cf_access_client_secret": FAKE_CF_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.usefixtures("clean_env")
class TestSecretFields:
    """Secrets are SecretStr and must not leak through repr/str/dumps."""

    def test_secret_fields_are_secretstr(self) -> None:
        """Test all three secret fields are SecretStr and expose values explicitly."""
        settings = _secret_settings()
        assert isinstance(settings.discord_bot_token, SecretStr)
        assert isinstance(settings.chat_bridge_token, SecretStr)
        assert isinstance(settings.cf_access_client_secret, SecretStr)
        assert settings.discord_bot_token.get_secret_value() == FAKE_DISCORD_TOKEN
        assert settings.chat_bridge_token.get_secret_value() == FAKE_BRIDGE_TOKEN
        assert settings.cf_access_client_secret.get_secret_value() == FAKE_CF_SECRET

    def test_repr_and_str_hide_secrets(self) -> None:
        """Test repr() and str() of Settings contain none of the secret values."""
        settings = _secret_settings()
        for rendered in (repr(settings), str(settings), f"{settings}", f"{settings!r}"):
            assert FAKE_DISCORD_TOKEN not in rendered
            assert FAKE_BRIDGE_TOKEN not in rendered
            assert FAKE_CF_SECRET not in rendered
            assert "**********" in rendered

    def test_dumps_hide_secrets(self) -> None:
        """Test model_dump() and model_dump_json() mask secret values."""
        settings = _secret_settings()
        dumped = settings.model_dump()
        for key in ("discord_bot_token", "chat_bridge_token", "cf_access_client_secret"):
            assert str(dumped[key]) == "**********"
        rendered = f"{dumped} {settings.model_dump_json()} {settings.model_dump(mode='json')}"
        assert FAKE_DISCORD_TOKEN not in rendered
        assert FAKE_BRIDGE_TOKEN not in rendered
        assert FAKE_CF_SECRET not in rendered
        assert "**********" in settings.model_dump_json()

    def test_validation_error_does_not_leak_secrets(self) -> None:
        """Test a failing validation elsewhere does not echo the secret values."""
        with pytest.raises(ValidationError) as exc_info:
            _secret_settings(api_port="0")
        message = str(exc_info.value)
        assert FAKE_DISCORD_TOKEN not in message
        assert FAKE_BRIDGE_TOKEN not in message
        assert FAKE_CF_SECRET not in message

    def test_missing_token_error_does_not_echo_env_secrets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test a missing required field does not dump the other env values in the error."""
        monkeypatch.setenv("CHAT_BRIDGE_TOKEN", FAKE_BRIDGE_TOKEN)
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", FAKE_CF_SECRET)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)
        message = str(exc_info.value)
        assert "DISCORD_BOT_TOKEN" in message
        assert FAKE_BRIDGE_TOKEN not in message
        assert FAKE_CF_SECRET not in message

    def test_optional_bridge_secrets_default_to_empty(self) -> None:
        """Test the optional bridge secrets default to an empty SecretStr."""
        settings = Settings(discord_bot_token="t", _env_file=None)
        assert isinstance(settings.chat_bridge_token, SecretStr)
        assert isinstance(settings.cf_access_client_secret, SecretStr)
        assert settings.chat_bridge_token.get_secret_value() == ""
        assert settings.cf_access_client_secret.get_secret_value() == ""
        assert settings.cf_access_client_id == ""

    def test_empty_bridge_secrets_are_valid(self) -> None:
        """Test explicitly empty bridge secrets are accepted (mirror is optional)."""
        settings = Settings(
            discord_bot_token="t",
            chat_bridge_token="",
            cf_access_client_secret="",
            _env_file=None,
        )
        assert settings.chat_bridge_token.get_secret_value() == ""
        assert settings.cf_access_client_secret.get_secret_value() == ""

    def test_secrets_loaded_from_env_aliases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test secrets are read from their environment variable aliases."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", FAKE_DISCORD_TOKEN)
        monkeypatch.setenv("CHAT_BRIDGE_TOKEN", FAKE_BRIDGE_TOKEN)
        monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "fake-cf-id")
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", FAKE_CF_SECRET)
        settings = Settings(_env_file=None)
        assert settings.discord_bot_token.get_secret_value() == FAKE_DISCORD_TOKEN
        assert settings.chat_bridge_token.get_secret_value() == FAKE_BRIDGE_TOKEN
        assert settings.cf_access_client_id == "fake-cf-id"
        assert settings.cf_access_client_secret.get_secret_value() == FAKE_CF_SECRET
        assert FAKE_DISCORD_TOKEN not in repr(settings)
        assert FAKE_BRIDGE_TOKEN not in repr(settings)
        assert FAKE_CF_SECRET not in repr(settings)


@pytest.mark.usefixtures("clean_env")
class TestChatBridgeUrl:
    """chat_bridge_url must be https (http only for local development)."""

    def test_default_is_valid_https(self) -> None:
        """Test the default bridge URL satisfies the validator."""
        settings = Settings(discord_bot_token="t", _env_file=None)
        assert settings.chat_bridge_url.startswith("https://")

    @pytest.mark.parametrize(
        "url",
        [
            "https://connect.apehost.net/dashboard/chat/bridge",
            "HTTPS://example.com/bridge",
            "https://example.com:8443/bridge",
            "http://localhost/bridge",
            "http://localhost:8787/bridge",
            "http://127.0.0.1:8787/bridge",
            "http://[::1]:8787/bridge",
            "https://localhost/bridge",
        ],
    )
    def test_accepts_https_and_local_http(self, url: str) -> None:
        """Test https URLs and http on loopback hosts are accepted."""
        settings = Settings(discord_bot_token="t", chat_bridge_url=url, _env_file=None)
        assert settings.chat_bridge_url == url

    def test_strips_whitespace(self) -> None:
        """Test surrounding whitespace is stripped from the URL."""
        settings = Settings(
            discord_bot_token="t",
            chat_bridge_url="  https://example.com/bridge \n",
            _env_file=None,
        )
        assert settings.chat_bridge_url == "https://example.com/bridge"

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/bridge",
            "http://connect.apehost.net/dashboard/chat/bridge",
            "http://localhost.evil.com/bridge",
            "http://127.0.0.1.evil.com/bridge",
            "http://localhost@evil.com/bridge",
            "http://10.0.0.5/bridge",
            "http://0.0.0.0/bridge",
        ],
    )
    def test_rejects_plain_http_for_remote_hosts(self, url: str) -> None:
        """Test plain http to a non-loopback host is rejected."""
        with pytest.raises(ValidationError, match="must use https"):
            Settings(discord_bot_token="t", chat_bridge_url=url, _env_file=None)

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/bridge",
            "ws://localhost/bridge",
            "file:///etc/passwd",
            "//example.com/bridge",
            "example.com/bridge",
            "https://",
            "",
        ],
    )
    def test_rejects_other_schemes_and_malformed(self, url: str) -> None:
        """Test non-http(s) schemes and URLs without a host are rejected."""
        with pytest.raises(ValidationError):
            Settings(discord_bot_token="t", chat_bridge_url=url, _env_file=None)

    def test_rejection_does_not_leak_secrets(self) -> None:
        """Test the https validation error never contains the secret values."""
        with pytest.raises(ValidationError) as exc_info:
            _secret_settings(chat_bridge_url="http://example.com/bridge")
        message = str(exc_info.value)
        assert FAKE_DISCORD_TOKEN not in message
        assert FAKE_BRIDGE_TOKEN not in message
        assert FAKE_CF_SECRET not in message

    def test_env_var_is_validated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test CHAT_BRIDGE_URL from the environment goes through the validator."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
        monkeypatch.setenv("CHAT_BRIDGE_URL", "http://example.com/bridge")
        with pytest.raises(ValidationError, match="must use https"):
            Settings(_env_file=None)
