"""FastAPI application factory."""

import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from wumpus_archiver.api.download_manager import DownloadManager
from wumpus_archiver.api.scrape_manager import ScrapeJobManager
from wumpus_archiver.api.transfer_manager import TransferManager
from wumpus_archiver.storage.database import Database, DatabaseRegistry

logger = logging.getLogger(__name__)


def create_app(
    database: Database,
    attachments_path: Path | None = None,
    discord_token: str | None = None,
    postgres_url: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        database: Database instance for storage
        attachments_path: Path to local attachments directory (enables local image serving)
        discord_token: Optional Discord bot token for scrape control panel

    Returns:
        Configured FastAPI application
    """

    # Build database registry
    registry = DatabaseRegistry()
    registry.register("sqlite", database, database.database_url)
    if postgres_url:
        pg_db = Database(postgres_url)
        registry.register("postgres", pg_db, postgres_url)
        # Default to PostgreSQL when available (primary storage in Docker)
        registry.set_active("postgres")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle."""
        await registry.connect_all()
        yield
        await registry.disconnect_all()

    app = FastAPI(
        title="Wumpus Archiver",
        description="Discord server archive exploration portal",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for SvelteKit dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Store database registry on app state (routes use get_db() via registry)
    app.state.db_registry = registry

    # Scrape control panel: manager + token
    app.state.scrape_manager = ScrapeJobManager(registry)
    app.state.transfer_manager = TransferManager(registry)
    app.state.download_manager = DownloadManager(registry.get_active(), attachments_path)
    # Try loading token from env/.env if not explicitly provided
    resolved_token = discord_token
    if not resolved_token:
        try:
            from wumpus_archiver.config import Settings

            settings = Settings()  # type: ignore[call-arg]
            resolved_token = settings.discord_bot_token
            logger.info("Loaded Discord bot token from settings — scrape control enabled")
        except Exception:
            logger.info("No Discord bot token found — scrape control panel will be read-only")
    app.state.discord_token = resolved_token

    # API authentication secret
    api_secret = None
    try:
        from wumpus_archiver.config import Settings as AuthSettings

        auth_s = AuthSettings()  # type: ignore[call-arg]
        api_secret = auth_s.api_secret
    except Exception:
        pass
    app.state.api_secret = api_secret
    if api_secret:
        logger.info("API authentication enabled")
    else:
        logger.info("API authentication disabled — set API_SECRET in .env to enable")

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

    @app.get("/api/auth/check")
    async def auth_check(request: Request) -> dict:
        """Check if auth is configured and if the request has a valid token."""
        secret = getattr(request.app.state, "api_secret", None)
        if secret is None:
            return {"authenticated": True, "auth_required": False}
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and hmac.compare_digest(auth_header[7:], secret):
            return {"authenticated": True, "auth_required": True}
        return {"authenticated": False, "auth_required": True}

    # Serve portal static files if built (SPA with fallback to index.html)
    portal_dist = Path(__file__).parent.parent.parent.parent / "portal" / "build"
    if portal_dist.exists():
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
            # Try serving exact file first (e.g. favicon.ico)
            file_path = (portal_dist / full_path).resolve()
            # Prevent path traversal — resolved path must stay within portal_dist
            if file_path.is_file() and str(file_path).startswith(str(portal_dist.resolve())):
                return FileResponse(str(file_path))
            # Fallback to index.html for SPA routing
            return FileResponse(str(portal_dist / "index.html"))

    return app

