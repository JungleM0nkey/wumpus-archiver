"""FastMCP server factory for wumpus-archiver."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastmcp import FastMCP

from wumpus_archiver.storage.database import Database

logger = logging.getLogger(__name__)

# Module-level config (not DB — that goes through lifespan)
_attachments_path: Path | None = None
_discord_token: str | None = None


@dataclass
class AppContext:
    """Lifespan context holding shared resources."""

    db: Database


def get_db() -> Database:
    """Get the Database from the current MCP request's lifespan context."""
    from fastmcp.server.dependencies import get_context

    ctx = get_context()
    rc = ctx.request_context
    if rc is None or rc.lifespan_context is None:
        raise RuntimeError("No active MCP request context — database unavailable")
    app_ctx: AppContext = rc.lifespan_context
    return app_ctx.db


def get_attachments_path() -> Path | None:
    """Get the attachments directory path."""
    return _attachments_path


def get_discord_token() -> str | None:
    """Get the Discord bot token."""
    return _discord_token


def create_mcp_server(
    db_path: Path,
    attachments_path: Path | None = None,
    discord_token: str | None = None,
) -> FastMCP:
    """Create and configure the MCP server.

    Args:
        db_path: Path to the SQLite database file.
        attachments_path: Path to the downloaded attachments directory.
        discord_token: Optional Discord bot token for scrape tools.

    Returns:
        Configured FastMCP instance ready to run.
    """
    global _attachments_path, _discord_token

    db_url = f"sqlite+aiosqlite:///{db_path.resolve()}"
    _attachments_path = attachments_path.resolve() if attachments_path else None
    _discord_token = discord_token

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        """Connect DB on startup, disconnect on shutdown."""
        db = Database(db_url)
        await db.connect()
        logger.info("MCP server connected to database: %s", db_url)
        try:
            yield AppContext(db=db)
        finally:
            await db.disconnect()
            logger.info("MCP server disconnected from database")

    mcp = FastMCP(
        name="wumpus-archiver",
        instructions=(
            "You are connected to a Discord server archive. "
            "Use tools to search messages, browse channels, view user profiles, "
            "get statistics, and manage scraping operations. "
            "Use resources to access archive data as context."
        ),
        lifespan=lifespan,
    )

    # Register components
    from wumpus_archiver.mcp.prompts import register_prompts
    from wumpus_archiver.mcp.resources import register_resources
    from wumpus_archiver.mcp.tools import register_tools

    register_tools(mcp)
    register_resources(mcp)
    register_prompts(mcp)

    return mcp

