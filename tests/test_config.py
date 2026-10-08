"""Tests for configuration management."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from wumpus_archiver.config import (
    DEFAULT_CHAT_BRIDGE_URL,
    Settings,
    validate_bridge_url,
)


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

    def test_token_required(self, monkeypatch) -> None:
        """Test that discord_bot_token is required."""
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    def test_token_must_not_be_blank(self, blank: str) -> None:
        """An empty or whitespace-only token is rejected, not stored."""
        with pytest.raises(ValidationError, match="must not be empty"):
            Settings(discord_bot_token=blank, _env_file=None)

    def test_blank_token_from_env_is_rejected(self, monkeypatch) -> None:
        """A blank DISCORD_BOT_TOKEN in the environment fails loading settings."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "")
        with pytest.raises(ValidationError, match="must not be empty"):
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
class TestValidateBridgeUrl:
    """validate_bridge_url: https (http only on loopback), no userinfo, sane port.

    This is the single rule set for where the bridge's secrets may be sent. It runs
    where the secrets are used (BridgeClient, mirror/backfill), never inside Settings.
    """

    def test_default_is_valid_https(self) -> None:
        """Test the default bridge URL satisfies the validator."""
        assert DEFAULT_CHAT_BRIDGE_URL.startswith("https://")
        assert validate_bridge_url(DEFAULT_CHAT_BRIDGE_URL) == DEFAULT_CHAT_BRIDGE_URL

    @pytest.mark.parametrize(
        "url",
        [
            "https://connect.apehost.net/dashboard/chat/bridge",
            "HTTPS://example.com/bridge",
            "https://example.com:8443/bridge",
            "http://localhost/bridge",
            "http://localhost:8787/bridge",
            "http://LOCALHOST:8787/bridge",
            "HTTP://127.0.0.1/bridge",
            "http://127.0.0.1:8787/bridge",
            "http://[::1]/bridge",
            "http://[::1]:8787/bridge",
            "https://localhost/bridge",
        ],
    )
    def test_accepts_https_and_local_http(self, url: str) -> None:
        """Test https URLs (any scheme case) and http on exact loopback hosts are accepted."""
        assert validate_bridge_url(url) == url

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  https://example.com/bridge \n", "https://example.com/bridge"),
            ("\thttp://127.0.0.1:8787/bridge  ", "http://127.0.0.1:8787/bridge"),
        ],
    )
    def test_strips_whitespace(self, raw: str, expected: str) -> None:
        """Test surrounding whitespace is stripped from the URL."""
        assert validate_bridge_url(raw) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/bridge",
            "http://connect.apehost.net/dashboard/chat/bridge",
            "http://localhost.evil.com/bridge",
            "http://localhost./bridge",
            "http://127.0.0.1.evil.com/bridge",
            "http://localhost@evil.com/bridge",
            "http://10.0.0.5/bridge",
            "http://0.0.0.0/bridge",
            "http://[::2]/bridge",
            "http://[::ffff:127.0.0.1]/bridge",
        ],
    )
    def test_rejects_plain_http_for_remote_hosts(self, url: str) -> None:
        """Test plain http to a non-loopback host is rejected."""
        with pytest.raises(ValueError, match="must use https"):
            validate_bridge_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/bridge",
            "ws://localhost/bridge",
            "file:///etc/passwd",
            "//example.com/bridge",
            "example.com/bridge",
            "https://",
            "https://:443/bridge",
            "http://[::1/bridge",
            "",
            "   ",
        ],
    )
    def test_rejects_other_schemes_and_malformed(self, url: str) -> None:
        """Test non-http(s) schemes and URLs without a host are rejected."""
        with pytest.raises(ValueError, match="CHAT_BRIDGE_URL"):
            validate_bridge_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://user:pw@example.com/bridge",
            "https://user@example.com/bridge",
            "https://:pw@example.com/bridge",
            "https://@example.com/bridge",
            "http://user:pw@localhost/bridge",
            "http://user:pw@127.0.0.1:8787/bridge",
            "http://user@[::1]:8787/bridge",
            "https://localhost@evil.com/bridge",
        ],
    )
    def test_rejects_userinfo(self, url: str) -> None:
        """Test URLs embedding a username/password are rejected (https and loopback)."""
        with pytest.raises(ValueError, match="must not contain credentials"):
            validate_bridge_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com:99999/bridge",
            "https://example.com:65536/bridge",
            "https://example.com:abc/bridge",
            "https://example.com:-1/bridge",
            "http://localhost:99999/bridge",
            "http://127.0.0.1:abc/bridge",
            "https://[::1]:99999/bridge",
        ],
    )
    def test_rejects_invalid_port(self, url: str) -> None:
        """Test a URL whose port does not parse (urlsplit raises) is rejected cleanly."""
        with pytest.raises(ValueError, match="invalid port") as exc_info:
            validate_bridge_url(url)
        # The urlsplit error quotes the offending text; it must not stay attached.
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__context__ is None

    @pytest.mark.parametrize(
        "url",
        [
            "http://user:SECRETMARK-pw@remote-host.example:99999/bridge?token=SECRETMARK-q",
            "https://user:SECRETMARK-pw@remote-host.example/bridge",
            "https://remote-host.example:SECRETMARK/bridge",
            "http://remote-host.example/SECRETMARK-path",
            "ftp://remote-host.example/SECRETMARK-path",
            "https://SECRETMARK℀.remote-host.example/bridge",
            "http://[SECRETMARK/bridge",
            "SECRETMARK-remote-host.example/bridge",
        ],
    )
    def test_errors_never_echo_the_url(self, url: str) -> None:
        """Test no rejection message (or chained cause) contains the URL or its parts."""
        with pytest.raises(ValueError) as exc_info:
            validate_bridge_url(url)
        shown = " ".join(
            str(e) for e in (exc_info.value, exc_info.value.__cause__, exc_info.value.__context__)
        )
        for fragment in ("SECRETMARK", "remote-host", url):
            assert fragment not in shown
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__context__ is None

    def test_errors_never_contain_other_secrets(self) -> None:
        """Test the other bridge secrets are not involved in (or leaked by) validation."""
        settings = _secret_settings(chat_bridge_url="http://example.com/bridge")
        with pytest.raises(ValueError) as exc_info:
            validate_bridge_url(settings.chat_bridge_url)
        message = str(exc_info.value)
        assert FAKE_DISCORD_TOKEN not in message
        assert FAKE_BRIDGE_TOKEN not in message
        assert FAKE_CF_SECRET not in message


@pytest.mark.usefixtures("clean_env")
class TestChatBridgeUrlSetting:
    """Settings never fails because of chat_bridge_url; enforcement lives at the point of use.

    A strict validator here broke every command (scrape, serve, create_app) for a blank or
    plain-http CHAT_BRIDGE_URL even though they never touch the bridge.
    """

    def test_default(self) -> None:
        """Test the default bridge URL is used when nothing is configured."""
        settings = Settings(discord_bot_token="t", _env_file=None)
        assert settings.chat_bridge_url == DEFAULT_CHAT_BRIDGE_URL

    @pytest.mark.parametrize("blank", ["", " ", "   ", "\t\n "])
    def test_blank_maps_to_default(self, blank: str) -> None:
        """Test a blank value falls back to the default URL instead of raising."""
        settings = Settings(discord_bot_token="t", chat_bridge_url=blank, _env_file=None)
        assert settings.chat_bridge_url == DEFAULT_CHAT_BRIDGE_URL

    def test_blank_env_var_maps_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test ``CHAT_BRIDGE_URL=`` in the environment does not break Settings()."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
        monkeypatch.setenv("CHAT_BRIDGE_URL", "")
        assert Settings(_env_file=None).chat_bridge_url == DEFAULT_CHAT_BRIDGE_URL

    def test_blank_dotenv_value_maps_to_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test ``CHAT_BRIDGE_URL=`` in a .env file does not break Settings()."""
        env_file = tmp_path / ".env"
        env_file.write_text("DISCORD_BOT_TOKEN=t\nCHAT_BRIDGE_URL=\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert Settings().chat_bridge_url == DEFAULT_CHAT_BRIDGE_URL

    def test_strips_whitespace(self) -> None:
        """Test surrounding whitespace is stripped from a configured URL."""
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
            "ftp://example.com/bridge",
            "https://user:pw@example.com/bridge",
            "https://example.com:99999/bridge",
            "example.com/bridge",
        ],
    )
    def test_settings_does_not_enforce_scheme_or_shape(self, url: str) -> None:
        """Test Settings accepts anything; validate_bridge_url is applied at the point of use."""
        settings = Settings(discord_bot_token="t", chat_bridge_url=url, _env_file=None)
        assert settings.chat_bridge_url == url
        with pytest.raises(ValueError):
            validate_bridge_url(settings.chat_bridge_url)

    def test_plain_http_env_var_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test a plain-http remote CHAT_BRIDGE_URL in the environment does not raise."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
        monkeypatch.setenv("CHAT_BRIDGE_URL", "http://example.com/bridge")
        settings = Settings(_env_file=None)
        assert settings.chat_bridge_url == "http://example.com/bridge"
