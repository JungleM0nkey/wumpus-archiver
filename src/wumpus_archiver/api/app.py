"""FastAPI application factory."""

import logging
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from wumpus_archiver.api.scrape_manager import ScrapeJobManager
from wumpus_archiver.storage.database import Database

logger = logging.getLogger(__name__)


def _load_api_security_settings() -> tuple[str | None, list[str]]:
    """Resolve the API auth token and allowed CORS origins from env/.env.

    ``Settings()`` requires ``DISCORD_BOT_TOKEN``, which a read-only portal deployment may
    not have, so a placeholder bot token is supplied: only the API fields are read here.
    If settings still cannot be loaded, fall back to the raw environment variables.

    Returns:
        Tuple of (API auth token or None, allowed CORS origins).
    """
    from pydantic import SecretStr

    from wumpus_archiver.config import DEFAULT_CORS_ORIGINS, Settings, parse_cors_origins

    try:
        settings = Settings(discord_bot_token=SecretStr("unused"))
        token = settings.api_auth_token.get_secret_value() if settings.api_auth_token else None
        return token, list(settings.cors_origins)
    except Exception:
        logger.warning("Could not load settings; reading API_AUTH_TOKEN/CORS_ORIGINS from env")

    env_token = os.environ.get("API_AUTH_TOKEN", "").strip() or None
    raw_origins = os.environ.get("CORS_ORIGINS")
    if raw_origins is None:
        return env_token, list(DEFAULT_CORS_ORIGINS)
    try:
        return env_token, parse_cors_origins(raw_origins)
    except ValueError:
        # Fail closed: an unparseable allow-list must not widen cross-origin access
        logger.warning("Invalid CORS_ORIGINS; no cross-origin requests will be allowed")
        return env_token, []


def create_app(
    database: Database,
    attachments_path: Path | None = None,
    discord_token: str | None = None,
    api_auth_token: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        database: Database instance for storage
        attachments_path: Path to local attachments directory (enables local image serving)
        discord_token: Optional Discord bot token for scrape control panel
        api_auth_token: Optional bearer token required for scrape start/cancel. If omitted,
            ``API_AUTH_TOKEN`` is read from the environment/.env; with no token at all,
            scrape control is disabled (those endpoints return 403).

    Returns:
        Configured FastAPI application
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle."""
        await database.connect()
        yield
        await database.disconnect()

    app = FastAPI(
        title="Wumpus Archiver",
        description="Discord server archive exploration portal",
        version="0.1.0",
        lifespan=lifespan,
    )

    env_auth_token, cors_origins = _load_api_security_settings()

    # CORS: only the configured origins (default: SvelteKit dev server + apehost dashboard).
    # Auth is a bearer header, not cookies, so credentials are never allowed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Store database on app state
    app.state.database = database

    # Bearer token guarding scrape start/cancel; None disables scrape control (fail closed)
    app.state.api_auth_token = api_auth_token or env_auth_token
    if not app.state.api_auth_token:
        logger.info("No API_AUTH_TOKEN set — scrape start/cancel are disabled")

    # Scrape control panel: manager + token
    app.state.scrape_manager = ScrapeJobManager(database)
    # Try loading token from env/.env if not explicitly provided
    resolved_token = discord_token
    if not resolved_token:
        try:
            from wumpus_archiver.config import Settings

            settings = Settings()  # type: ignore[call-arg]
            resolved_token = settings.discord_bot_token.get_secret_value()
            logger.info("Loaded Discord bot token from settings — scrape control enabled")
        except Exception:
            logger.info("No Discord bot token found — scrape control panel will be read-only")
    app.state.discord_token = resolved_token

    # Store and serve local attachments if path provided
    resolved_attachments: Path | None = None
    if attachments_path:
        resolved_attachments = attachments_path.resolve()
        if resolved_attachments.exists():
            app.mount(
                "/attachments",
                StaticFiles(directory=str(resolved_attachments)),
                name="attachments",
            )
    app.state.attachments_path = resolved_attachments

    # Register API routes
    from wumpus_archiver.api.routes import router as api_router  # noqa: PLC0415

    app.include_router(api_router, prefix="/api")

    # Serve portal static files if built (SPA with fallback to index.html)
    portal_dist = _portal_dist()
    if portal_dist.exists():
        portal_root = portal_dist.resolve()
        from fastapi.responses import FileResponse

        # Mount static assets (JS, CSS, etc.) at /_app/
        app_assets = portal_dist / "_app"
        if app_assets.exists():
            app.mount(
                "/_app",
                StaticFiles(directory=str(app_assets)),
                name="portal_assets",
            )

        # Serve robots.txt and other root-level static files
        @app.get("/robots.txt", include_in_schema=False)
        async def robots_txt() -> FileResponse:
            return FileResponse(str(portal_dist / "robots.txt"))

        # SPA fallback: serve index.html for all unmatched routes
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # Try serving exact file first (e.g. favicon.ico), but never anything
            # that resolves outside the build directory.
            file_path = _resolve_portal_file(portal_root, full_path)
            if file_path is not None:
                return FileResponse(str(file_path))
            # Fallback to index.html for SPA routing
            return FileResponse(str(portal_dist / "index.html"))

    return app


def _portal_dist() -> Path:
    """Return the directory containing the built SvelteKit portal.

    Returns:
        Path to ``portal/build`` (it may not exist if the portal was not built)
    """
    return Path(__file__).parent.parent.parent.parent / "portal" / "build"


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
