"""Configuration management."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import SplitResult, urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Origins allowed to call the API cross-origin unless CORS_ORIGINS overrides them:
# the SvelteKit dev server, local backends, and the apehost dashboard.
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8000",
    "https://connect.apehost.net",
)


def parse_cors_origins(value: str) -> list[str]:
    """Parse a CORS origin list from an environment string.

    Accepts a comma-separated list (``http://a.example,http://b.example``) or a JSON
    array of strings. Whitespace, empty entries and trailing slashes are dropped.

    Args:
        value: Raw string, e.g. the value of the ``CORS_ORIGINS`` environment variable.

    Returns:
        List of origins (empty if ``value`` is blank).

    Raises:
        ValueError: If ``value`` looks like a JSON array but is not a list of strings.
    """
    text = value.strip()
    items: list[str]
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"CORS_ORIGINS looks like JSON but is not valid: {e}") from e
        if not isinstance(parsed, list) or not all(isinstance(i, str) for i in parsed):
            raise ValueError("CORS_ORIGINS JSON value must be a list of strings")
        items = parsed
    else:
        items = text.split(",")
    return [origin.strip().rstrip("/") for origin in items if origin.strip()]


# Hosts for which a plain-http bridge URL is tolerated (local development only).
_LOCAL_BRIDGE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

DEFAULT_CHAT_BRIDGE_URL = "https://connect.apehost.net/dashboard/chat/bridge"


def validate_bridge_url(url: str) -> str:
    """Validate a chat bridge URL, i.e. a place where bridge secrets will be sent.

    The bridge client sends a bearer token and Cloudflare Access credentials with every
    request, so the URL must be absolute, use https (http only for localhost, 127.0.0.1 or
    [::1] development), carry no username/password and have a parseable port.

    This runs where the secrets are used (``BridgeClient``, the ``mirror`` and ``backfill``
    commands), not in ``Settings``: a bad value must not break commands that never use the
    bridge.

    Args:
        url: Candidate bridge URL; surrounding whitespace is stripped.

    Returns:
        The stripped URL.

    Raises:
        ValueError: If the URL is not acceptable. The message never includes the URL (it may
            embed credentials), and the parser's own error, which quotes the offending text,
            is neither chained nor kept as ``__context__``.
    """
    url = url.strip()
    parts: SplitResult | None
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
    except ValueError:
        parts = hostname = None
    if parts is None:
        # Raised outside the except block so the parser's error is not attached
        raise ValueError("CHAT_BRIDGE_URL is not a valid URL")
    if not hostname:
        raise ValueError("CHAT_BRIDGE_URL must be an absolute URL with a host")
    local_http = parts.scheme == "http" and hostname in _LOCAL_BRIDGE_HOSTS
    if parts.scheme != "https" and not local_http:
        raise ValueError(
            "CHAT_BRIDGE_URL must use https:// "
            "(http:// is only allowed for localhost, 127.0.0.1 or [::1])"
        )
    if "@" in parts.netloc:
        raise ValueError("CHAT_BRIDGE_URL must not contain credentials (username/password)")
    try:
        _ = parts.port  # reading it parses and range-checks the port
        port_ok = True
    except ValueError:
        port_ok = False
    if not port_ok:
        raise ValueError("CHAT_BRIDGE_URL has an invalid port")
    return url


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        # Validation errors otherwise echo the raw input (every env value, secrets
        # included) when a required field is missing; the CLI prints these errors.
        hide_input_in_errors=True,
    )

    # Discord
    discord_bot_token: SecretStr = Field(..., validation_alias="DISCORD_BOT_TOKEN")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./wumpus_archive.db",
        validation_alias="DATABASE_URL",
    )

    # API
    api_host: str = Field(default="127.0.0.1", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    api_debug: bool = Field(default=False, validation_alias="API_DEBUG")

    # API security
    # Bearer token required for state-changing scrape endpoints. Unset = scrape control disabled.
    api_auth_token: SecretStr | None = Field(default=None, validation_alias="API_AUTH_TOKEN")
    # Browser origins allowed to call the API (comma-separated in CORS_ORIGINS).
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS),
        validation_alias="CORS_ORIGINS",
    )

    # Target server
    guild_id: int | None = Field(default=None, validation_alias="GUILD_ID")

    # Scraper
    batch_size: int = Field(default=1000, validation_alias="BATCH_SIZE")
    rate_limit_delay: float = Field(default=0.5, validation_alias="RATE_LIMIT_DELAY")
    max_retries: int = Field(default=5, validation_alias="MAX_RETRIES")
    download_attachments: bool = Field(default=True, validation_alias="DOWNLOAD_ATTACHMENTS")
    attachments_path: Path = Field(
        default=Path("./attachments"), validation_alias="ATTACHMENTS_PATH"
    )

    # Portal
    portal_title: str = Field(default="Wumpus Archiver", validation_alias="PORTAL_TITLE")
    portal_description: str = Field(
        default="Discord Server Archive", validation_alias="PORTAL_DESCRIPTION"
    )
    default_page_size: int = Field(default=50, validation_alias="DEFAULT_PAGE_SIZE")

    # Chat mirror bridge (wumpus-archiver mirror)
    # Not validated here: see validate_bridge_url(), applied where the bridge is used.
    chat_bridge_url: str = Field(
        default=DEFAULT_CHAT_BRIDGE_URL,
        validation_alias="CHAT_BRIDGE_URL",
    )
    chat_bridge_token: SecretStr = Field(
        default=SecretStr(""), validation_alias="CHAT_BRIDGE_TOKEN"
    )
    cf_access_client_id: str = Field(default="", validation_alias="CF_ACCESS_CLIENT_ID")
    cf_access_client_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="CF_ACCESS_CLIENT_SECRET"
    )

    # Logging
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_file: Path | None = Field(default=None, validation_alias="LOG_FILE")

    @field_validator("discord_bot_token")
    @classmethod
    def validate_token_not_blank(cls, v: SecretStr) -> SecretStr:
        """Reject an empty or whitespace-only bot token.

        A blank value usually comes from a placeholder in .env or an unset shell
        variable; accepting it would let a scrape reach the Discord gateway with
        no credential and hang there.
        """
        if not v.get_secret_value().strip():
            raise ValueError("DISCORD_BOT_TOKEN must not be empty")
        return v

    @field_validator("chat_bridge_url", mode="before")
    @classmethod
    def blank_bridge_url_is_default(cls, v: object) -> object:
        """Strip whitespace and treat a blank bridge URL as unset (the default URL).

        Deliberately lenient: Settings is shared by every command, so a blank or plain-http
        CHAT_BRIDGE_URL must not make it fail for commands that never use the bridge.
        ``validate_bridge_url`` enforces the real rules where the secrets are sent.
        """
        if isinstance(v, str):
            return v.strip() or DEFAULT_CHAT_BRIDGE_URL
        return v

    @field_validator("api_auth_token", mode="before")
    @classmethod
    def blank_auth_token_is_none(cls, v: object) -> object:
        """Treat an empty or whitespace-only API auth token as unset."""
        if isinstance(v, SecretStr):
            v = v.get_secret_value()
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, v: object) -> object:
        """Allow CORS_ORIGINS to be a plain comma-separated string."""
        if isinstance(v, str):
            return parse_cors_origins(v)
        return v

    @field_validator("api_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port is in valid range."""
        if not 1 <= v <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        """Validate batch size is positive."""
        if v < 1:
            raise ValueError(f"Batch size must be positive, got {v}")
        return v

    @field_validator("default_page_size")
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        """Validate page size is in reasonable range."""
        if not 1 <= v <= 1000:
            raise ValueError(f"Page size must be between 1 and 1000, got {v}")
        return v

    @field_validator("rate_limit_delay")
    @classmethod
    def validate_rate_limit_delay(cls, v: float) -> float:
        """Validate rate limit delay is non-negative."""
        if v < 0:
            raise ValueError(f"Rate limit delay must be non-negative, got {v}")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Validate max retries is non-negative."""
        if v < 0:
            raise ValueError(f"Max retries must be non-negative, got {v}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is recognized."""
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Log level must be one of {valid}, got {v}")
        return v.upper()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]


def optional_bot_token() -> str | None:
    """The bot token from the environment or ``.env``, or ``None``.

    ``None`` means no usable token: the variable is unset, empty or whitespace.
    This is the only way composition roots (``serve``, the dev module) decide
    whether scrape control is enabled; the API itself never reads settings.

    Raises:
        ValidationError: If settings are invalid for any other reason (for
            example a bad ``API_PORT``), so a misconfiguration is reported
            rather than silently read as "no token".
    """
    try:
        return Settings().discord_bot_token.get_secret_value()  # type: ignore[call-arg]
    except ValidationError as exc:
        if all(error["loc"] == ("DISCORD_BOT_TOKEN",) for error in exc.errors()):
            return None
        raise
