"""FastAPI application factory.

``create_app`` is a pure function of the collaborators it is handed. It reads
nothing from the environment, the working directory, ``.env`` or the package
location; the composition roots (``wumpus-archiver serve``, the dev module, the
test fixtures) resolve those and pass values in. See ``wumpus_archiver.compose``
for the helpers they share.
"""

import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr

from wumpus_archiver.api.deps import Wiring, bind
from wumpus_archiver.api.scrape_control import ReadOnlyScrape, ScrapeControl
from wumpus_archiver.storage.database import Database


def create_app(
    database: Database,
    *,
    attachments_dir: Path | None = None,
    portal_build: Path | None = None,
    scrape: ScrapeControl | None = None,
    api_auth_token: SecretStr | str | None = None,
    cors_origins: Sequence[str] = (),
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
        api_auth_token: Bearer token that ``POST /api/scrape/start`` and
            ``/api/scrape/cancel`` require. ``None`` or blank disables both (403):
            scrape control fails closed.
        cors_origins: Browser origins allowed to call the API cross-origin. The
            default allows none; the composition roots pass the configured list.

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

    # CORS: only the origins handed in. Auth is a bearer header, not cookies, so
    # credentials are never allowed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    if isinstance(api_auth_token, str):
        api_auth_token = SecretStr(api_auth_token)
    if api_auth_token is not None and not api_auth_token.get_secret_value().strip():
        api_auth_token = None

    resolved_attachments = attachments_dir.resolve() if attachments_dir is not None else None
    bind(
        app,
        Wiring(
            database=database,
            attachments_dir=resolved_attachments,
            portal_build=portal_build.resolve() if portal_build is not None else None,
            scrape=scrape if scrape is not None else ReadOnlyScrape(),
            api_auth_token=api_auth_token,
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

    # robots.txt is a 404 rather than the SPA entry point when the build has none.
    @app.get("/robots.txt", include_in_schema=False)
    async def robots_txt() -> FileResponse:
        robots = _resolve_portal_file(portal_root, "robots.txt")
        if robots is None:
            raise HTTPException(status_code=404)
        return FileResponse(str(robots))

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


# ``Path.resolve()`` is quadratic in the number of path segments and runs on the event loop,
# so untrusted request paths are bounded before it. Real build output (for example
# ``_app/immutable/chunks/<hash>.js``) is far below both caps.
_MAX_REQUEST_PATH_CHARS = 1024
_MAX_REQUEST_PATH_SEGMENTS = 64


def _resolve_portal_file(portal_root: Path, requested: str) -> Path | None:
    """Map a request path to a file inside the portal build directory.

    The request path is untrusted (it is URL-decoded before routing), so it is checked in
    layers, cheapest first, and the filesystem is only touched once the path is proven to
    stay inside ``portal_root``:

    1. size caps and a NUL/backslash guard;
    2. a lexical check - ``..`` segments are collapsed with ``os.path.normpath`` (linear, no
       filesystem access) and anything that is not under ``portal_root`` is rejected;
    3. one ``stat``: only an existing regular file goes on, so a junk request cannot stall
       the event loop in the quadratic ``resolve()``;
    4. ``resolve()`` follows symlinks and the final location must still be inside
       ``portal_root`` (a symlink in the build directory cannot lead outside it).

    Args:
        portal_root: Resolved absolute path of the portal build directory
        requested: Request path relative to the site root (URL-decoded)

    Returns:
        The resolved file path, or None if the path is empty, malformed, too long,
        escapes ``portal_root`` or is not a regular file
    """
    if not requested or "\x00" in requested or "\\" in requested:
        return None
    if (
        len(requested) > _MAX_REQUEST_PATH_CHARS
        or requested.count("/") + 1 > _MAX_REQUEST_PATH_SEGMENTS
    ):
        return None
    root = str(portal_root)
    # An absolute `requested` replaces `root` in join(); the prefix check below rejects it.
    candidate = os.path.normpath(os.path.join(root, requested))
    if not candidate.startswith(root.rstrip(os.sep) + os.sep):
        return None
    try:
        path = Path(candidate)
        if not path.is_file():
            # Cheap single stat; ENAMETOOLONG and friends land in the except below.
            return None
        resolved = path.resolve()
        if resolved.is_relative_to(portal_root) and resolved.is_file():
            return resolved
    except (OSError, ValueError, RuntimeError):
        # Unresolvable (e.g. symlink loop, over-long name) -> treat as not found
        return None
    return None
