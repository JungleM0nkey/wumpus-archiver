"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from wumpus_archiver.api.scrape_manager import ScrapeJobManager
from wumpus_archiver.storage.database import Database

logger = logging.getLogger(__name__)


def create_app(
    database: Database,
    attachments_path: Path | None = None,
    discord_token: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        database: Database instance for storage
        attachments_path: Path to local attachments directory (enables local image serving)
        discord_token: Optional Discord bot token for scrape control panel

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

    # CORS for SvelteKit dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store database on app state
    app.state.database = database

    # Scrape control panel: manager + token
    app.state.scrape_manager = ScrapeJobManager(database)
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
            file_path = portal_dist / full_path
            if file_path.is_file():
                return FileResponse(str(file_path))
            # Fallback to index.html for SPA routing
            return FileResponse(str(portal_dist / "index.html"))

    return app

