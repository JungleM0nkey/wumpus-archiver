"""FastAPI application factory.

``create_app`` is a pure function of the collaborators it is handed. It reads
nothing from the environment, the working directory, ``.env`` or the package
location; the composition roots (``wumpus-archiver serve``, the dev module, the
test fixtures) resolve those and pass values in. See ``wumpus_archiver.compose``
for the helpers they share.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from wumpus_archiver.api.deps import Wiring, bind
from wumpus_archiver.api.scrape_control import ReadOnlyScrape, ScrapeControl
from wumpus_archiver.storage.database import Database


def create_app(
    database: Database,
    *,
    attachments_dir: Path | None = None,
    portal_build: Path | None = None,
    scrape: ScrapeControl | None = None,
) -> FastAPI:
    """Build the portal app from the collaborators handed in.

    The factory never touches the database at construction time. The database
    must be connected, with its schema present, before the first ``/api`` request
    is served. The app's lifespan follows one rule (see ADR 0001): on startup it
    connects the database only if it is not already connected, and on shutdown it
    disconnects only what it connected. An ASGI server therefore owns the
    connection of a fresh ``Database``, while a test fixture that connected the
    database itself keeps owning it.

    Routes are mounted in this order, and the order is part of the contract:
    CORS, ``/attachments``, the ``/api`` router, then the portal (``/_app``,
    ``/robots.txt`` and the SPA fallback last), so every defined ``/api`` route
    wins over the fallback.

    Args:
        database: The archive to serve.
        attachments_dir: Directory of local attachments, served at ``/attachments``.
            ``None`` means attachment URLs stay on the Discord CDN. A given path
            must be an existing directory; a missing one raises rather than being
            silently skipped.
        portal_build: The portal's built static output, served as a single-page
            app with a fallback to its ``index.html``. ``None`` means API only:
            ``/`` is a 404. A given path must contain ``index.html``.
        scrape: Scrape control for the ``/api/scrape`` routes. ``None`` means the
            control is read-only (no bot token was configured).

    Returns:
        The configured FastAPI application.

    Raises:
        RuntimeError: If ``attachments_dir`` is not an existing directory.
        FileNotFoundError: If ``portal_build`` has no ``index.html``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Connect the database if nobody else did; disconnect only what we connected."""
        owns_connection = not database.connected
        if owns_connection:
            await database.connect()
        try:
            yield
        finally:
            if owns_connection:
                await database.disconnect()

    app = FastAPI(
        title="Wumpus Archiver",
        description="Discord server archive exploration portal",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for SvelteKit dev server + the apehost dashboard
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8000",
            "https://connect.apehost.net",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    resolved_attachments = attachments_dir.resolve() if attachments_dir is not None else None
    bind(
        app,
        Wiring(
            database=database,
            attachments_dir=resolved_attachments,
            portal_build=portal_build.resolve() if portal_build is not None else None,
            scrape=scrape if scrape is not None else ReadOnlyScrape(),
        ),
    )

    if resolved_attachments is not None:
        # StaticFiles raises RuntimeError when the directory does not exist.
        app.mount(
            "/attachments",
            StaticFiles(directory=str(resolved_attachments)),
            name="attachments",
        )

    from wumpus_archiver.api.routes import router as api_router  # noqa: PLC0415

    app.include_router(api_router, prefix="/api")

    if portal_build is not None:
        _mount_portal(app, portal_build.resolve())

    return app


def _mount_portal(app: FastAPI, portal_root: Path) -> None:
    """Serve the portal build as a single-page app with a guarded fallback.

    Args:
        app: The app to mount on; the ``/api`` router must already be included.
        portal_root: Resolved absolute path of the portal build directory.

    Raises:
        FileNotFoundError: If the directory has no ``index.html``.
    """
    index_html = portal_root / "index.html"
    if not index_html.is_file():
        raise FileNotFoundError(f"portal build has no index.html: {portal_root}")

    # Mount static assets (JS, CSS, etc.) at /_app/
    app_assets = portal_root / "_app"
    if app_assets.is_dir():
        app.mount(
            "/_app",
            StaticFiles(directory=str(app_assets)),
            name="portal_assets",
        )

    # Serve robots.txt and other root-level static files
    @app.get("/robots.txt", include_in_schema=False)
    async def robots_txt() -> FileResponse:
        return FileResponse(str(portal_root / "robots.txt"))

    # SPA fallback: serve index.html for all unmatched routes
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Try serving exact file first (e.g. favicon.ico), but never anything
        # that resolves outside the build directory.
        file_path = _resolve_portal_file(portal_root, full_path)
        if file_path is not None:
            return FileResponse(str(file_path))
        # Fallback to index.html for SPA routing
        return FileResponse(str(index_html))


def _resolve_portal_file(portal_root: Path, requested: str) -> Path | None:
    """Map a request path to a file inside the portal build directory.

    The request path is untrusted (it is URL-decoded before routing), so the
    candidate is fully resolved (``..`` segments and symlinks) and only returned
    if it is a regular file located inside ``portal_root``.

    Args:
        portal_root: Resolved absolute path of the portal build directory
        requested: Request path relative to the site root (URL-decoded)

    Returns:
        The resolved file path, or None if the path is empty, malformed, escapes
        ``portal_root`` or is not a regular file
    """
    if not requested or "\x00" in requested or "\\" in requested:
        return None
    try:
        # An absolute `requested` replaces portal_root here; the containment check rejects it.
        candidate = (portal_root / requested).resolve()
        if candidate.is_relative_to(portal_root) and candidate.is_file():
            return candidate
    except (OSError, ValueError, RuntimeError):
        # Unresolvable (e.g. symlink loop, over-long name) -> treat as not found
        return None
    return None
