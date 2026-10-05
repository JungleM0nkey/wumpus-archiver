"""Configuration management."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
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
    chat_bridge_url: str = Field(
        default="https://connect.apehost.net/dashboard/chat/bridge",
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

    @field_validator("chat_bridge_url")
    @classmethod
    def validate_chat_bridge_url(cls, v: str) -> str:
        """Require https for the bridge URL (http only for localhost development).

        The bridge client sends bearer and Cloudflare Access credentials with every
        request, so a plain-http remote URL would leak them in cleartext.
        """
        v = v.strip()
        parts = urlsplit(v)
        if not parts.hostname:
            raise ValueError("CHAT_BRIDGE_URL must be an absolute URL with a host")
        if parts.scheme == "https":
            return v
        if parts.scheme == "http" and parts.hostname in _LOCAL_BRIDGE_HOSTS:
            return v
        raise ValueError(
            "CHAT_BRIDGE_URL must use https:// "
            "(http:// is only allowed for localhost, 127.0.0.1 or [::1])"
        )

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
