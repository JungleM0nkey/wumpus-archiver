"""How route handlers receive the collaborators the app was built with.

``create_app`` binds a :class:`Wiring` to the app it returns. Handlers declare
:data:`Db`, :data:`AttachmentsDir` or :data:`Scrape` in their signature and
FastAPI resolves them per request. Nothing else in the package spells the
``app.state`` attribute this module keeps the wiring under; an app that includes
the API router without going through ``create_app`` fails every request with
:class:`NotWiredError` rather than an attribute error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request

from wumpus_archiver.api.scrape_control import ScrapeControl
from wumpus_archiver.storage.database import Database


@dataclass(frozen=True, slots=True)
class Wiring:
    """What ``create_app`` was handed, exactly as handed.

    Attributes:
        database: The archive. Must be connected, with its schema present, before
            the first ``/api`` request is served; see the lifespan rule on
            ``create_app`` for who connects it.
        attachments_dir: Directory of local attachments, mounted at
            ``/attachments``; ``None`` means attachment URLs stay on the CDN.
        portal_build: The portal's built output, served as the SPA; ``None``
            means the app is API-only. No handler reads this; it is kept so
            ``wiring_of`` can answer what the app was built with.
        scrape: Scrape control. Never ``None``: ``create_app`` substitutes
            ``ReadOnlyScrape`` when no adapter is given.
    """

    database: Database
    attachments_dir: Path | None
    portal_build: Path | None
    scrape: ScrapeControl


class NotWiredError(RuntimeError):
    """A handler ran on an app that was not built by ``create_app``."""


_STATE_ATTR = "wumpus_wiring"


def bind(app: FastAPI, wiring: Wiring) -> None:
    """Attach ``wiring`` to ``app``. Called once, by ``create_app``.

    Raises:
        RuntimeError: If the app already carries a wiring.
    """
    if getattr(app.state, _STATE_ATTR, None) is not None:
        raise RuntimeError("this app is already wired")
    setattr(app.state, _STATE_ATTR, wiring)


def wiring_of(app: FastAPI) -> Wiring:
    """The wiring ``create_app`` bound to ``app``.

    Raises:
        NotWiredError: If the app was not built by ``create_app``.
    """
    wiring = getattr(app.state, _STATE_ATTR, None)
    if wiring is None:
        raise NotWiredError(
            "this app was not built by wumpus_archiver.api.app.create_app(); "
            "route handlers have no database, attachments dir or scrape control"
        )
    return wiring  # type: ignore[no-any-return]


def get_db(request: Request) -> Database:
    """Dependency: the archive database."""
    return wiring_of(request.app).database


def get_attachments_dir(request: Request) -> Path | None:
    """Dependency: the local attachments directory, or ``None``."""
    return wiring_of(request.app).attachments_dir


def get_scrape(request: Request) -> ScrapeControl:
    """Dependency: scrape control (read-only when no token was configured)."""
    return wiring_of(request.app).scrape


Db = Annotated[Database, Depends(get_db)]
AttachmentsDir = Annotated[Path | None, Depends(get_attachments_dir)]
Scrape = Annotated[ScrapeControl, Depends(get_scrape)]


__all__ = [
    "AttachmentsDir",
    "Db",
    "NotWiredError",
    "Scrape",
    "Wiring",
    "get_attachments_dir",
    "get_db",
    "get_scrape",
    "wiring_of",
]
