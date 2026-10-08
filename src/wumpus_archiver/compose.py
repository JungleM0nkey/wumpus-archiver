"""Composition helpers shared by the places that build the app.

``wumpus-archiver serve`` and the dev module both have to answer the same
questions before calling ``create_app``: is a bot token configured, which API
token guards scrape control and which origins may call the API, and where is the
portal build? The answers come from the environment and the file system, which
the factory itself never reads. Nothing under ``wumpus_archiver.api`` imports
this module.
"""

import logging
import os
from pathlib import Path

from pydantic import SecretStr

from wumpus_archiver.api.scrape_control import ReadOnlyScrape, ScrapeControl
from wumpus_archiver.config import (
    DEFAULT_CORS_ORIGINS,
    Settings,
    optional_bot_token,
    parse_cors_origins,
)
from wumpus_archiver.storage.database import Database

logger = logging.getLogger(__name__)


def scrape_from_settings(database: Database) -> ScrapeControl:
    """Scrape control for ``database``: enabled if a bot token is configured, else read-only.

    The token comes from ``DISCORD_BOT_TOKEN`` in the environment or ``.env`` in
    the working directory; unset or blank means read-only.
    """
    token = optional_bot_token()
    if token is None:
        return ReadOnlyScrape()
    from wumpus_archiver.api.scrape_manager import ScrapeJobManager  # noqa: PLC0415

    return ScrapeJobManager(database, token)


def api_security_from_settings() -> tuple[SecretStr | None, list[str]]:
    """The API auth token and the allowed CORS origins, from the environment or ``.env``.

    ``Settings()`` requires ``DISCORD_BOT_TOKEN``, which a read-only portal deployment
    may not have, so a placeholder bot token is supplied: only the API fields are read.
    If settings still cannot be loaded, the raw environment variables are read instead.
    An unset or blank token leaves scrape start/cancel disabled, and an unparseable
    ``CORS_ORIGINS`` allows no cross-origin requests: both fail closed.

    Returns:
        The API auth token (``None`` when unset) and the allowed CORS origins.
    """
    try:
        settings = Settings(discord_bot_token=SecretStr("unused"))
        return settings.api_auth_token, list(settings.cors_origins)
    except Exception:
        logger.warning("Could not load settings; reading API_AUTH_TOKEN/CORS_ORIGINS from env")

    raw_token = os.environ.get("API_AUTH_TOKEN", "").strip()
    token = SecretStr(raw_token) if raw_token else None
    raw_origins = os.environ.get("CORS_ORIGINS")
    if raw_origins is None:
        return token, list(DEFAULT_CORS_ORIGINS)
    try:
        return token, parse_cors_origins(raw_origins)
    except ValueError:
        # Fail closed: an unparseable allow-list must not widen cross-origin access
        logger.warning("Invalid CORS_ORIGINS; no cross-origin requests will be allowed")
        return token, []


def portal_build_dir() -> Path | None:
    """The portal build to serve, or ``None`` when no built portal is found.

    Looks for ``portal/build/index.html`` beside the source tree, then under the
    working directory. Only the build output is needed: a deployment may ship
    ``portal/build`` without the portal's sources or ``package.json``.
    """
    for portal in (Path(__file__).resolve().parents[2] / "portal", Path.cwd() / "portal"):
        build = portal / "build"
        if (build / "index.html").is_file():
            return build
    return None


__all__ = ["api_security_from_settings", "portal_build_dir", "scrape_from_settings"]
