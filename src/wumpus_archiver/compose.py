"""Composition helpers shared by the places that build the app.

``wumpus-archiver serve`` and the dev module both have to answer the same
questions before calling ``create_app``: is a bot token configured, which API
token guards scrape control and which origins may call the API, and where is the
portal build? The answers come from the environment and the file system, which
the factory itself never reads. Nothing under ``wumpus_archiver.api`` imports
this module.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import SecretStr

from wumpus_archiver.api.scrape_control import ReadOnlyScrape, ScrapeControl
from wumpus_archiver.config import ServeSettings
from wumpus_archiver.storage.database import Database


@dataclass(frozen=True)
class ServeConfig:
    """What the composition roots read from settings, loaded once.

    Both tokens are ``SecretStr`` so a repr of this never shows them.

    Attributes:
        bot_token: The bot token, or ``None`` when unset or blank (read-only scrape control).
        api_auth_token: The token guarding scrape start/cancel, or ``None`` when unset
            or blank (both disabled).
        cors_origins: Browser origins allowed to call the API cross-origin.
    """

    bot_token: SecretStr | None
    api_auth_token: SecretStr | None
    cors_origins: tuple[str, ...]


def serve_config() -> ServeConfig:
    """The bot token, API auth token and CORS origins, from the environment or ``.env``.

    One ``ServeSettings`` load answers all three, so they always come from the
    same configuration. Startup fails closed: a missing or blank token disables
    what it guards, and any invalid setting raises instead of being guessed around.

    Raises:
        ValidationError: If any setting is invalid (for example a bad ``API_PORT``
            or an unparseable ``CORS_ORIGINS``).
    """
    settings = ServeSettings()
    return ServeConfig(
        bot_token=settings.discord_bot_token,
        api_auth_token=settings.api_auth_token,
        cors_origins=tuple(settings.cors_origins),
    )


def scrape_control(database: Database, bot_token: SecretStr | None) -> ScrapeControl:
    """Scrape control for ``database``: enabled with a bot token, else read-only."""
    if bot_token is None:
        return ReadOnlyScrape()
    from wumpus_archiver.api.scrape_manager import ScrapeJobManager  # noqa: PLC0415

    return ScrapeJobManager(database, bot_token.get_secret_value())


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


__all__ = ["ServeConfig", "portal_build_dir", "scrape_control", "serve_config"]
