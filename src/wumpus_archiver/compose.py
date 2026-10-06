"""Composition helpers shared by the places that build the app.

``wumpus-archiver serve`` and the dev module both have to answer the same two
questions before calling ``create_app``: is a bot token configured, and where
is the portal build? The answers come from the environment and the file system,
which the factory itself never reads. Nothing under ``wumpus_archiver.api``
imports this module.
"""

from pathlib import Path

from wumpus_archiver.api.scrape_control import ReadOnlyScrape, ScrapeControl
from wumpus_archiver.config import optional_bot_token
from wumpus_archiver.storage.database import Database
from wumpus_archiver.utils.process_manager import resolve_portal_dir


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


def portal_build_dir() -> Path | None:
    """The portal build to serve, or ``None`` when the portal is absent or not built."""
    try:
        portal_dir = resolve_portal_dir()
    except FileNotFoundError:
        return None
    build = portal_dir / "build"
    return build if (build / "index.html").is_file() else None


__all__ = ["portal_build_dir", "scrape_from_settings"]
