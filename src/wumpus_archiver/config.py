"""Configuration management."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Discord
    discord_bot_token: str = Field(..., validation_alias="DISCORD_BOT_TOKEN")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./wumpus_archive.db",
        validation_alias="DATABASE_URL",
    )

    # API
    api_host: str = Field(default="127.0.0.1", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    api_debug: bool = Field(default=False, validation_alias="API_DEBUG")

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

    # Logging
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_file: Path | None = Field(default=None, validation_alias="LOG_FILE")

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
