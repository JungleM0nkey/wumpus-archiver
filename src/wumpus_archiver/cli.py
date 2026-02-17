"""Command-line interface for wumpus-archiver."""

import asyncio
import sys
from pathlib import Path
from typing import cast

from importlib.metadata import version as pkg_version

import click

from wumpus_archiver.bot.scraper import ArchiverBot
from wumpus_archiver.config import Settings
from wumpus_archiver.storage.database import Database


@click.group()
@click.version_option(version=pkg_version("wumpus-archiver"))
def cli() -> None:
    """Wumpus Archiver - Discord server archival system."""
    pass


@cli.command()
@click.option(
    "--guild-id",
    type=int,
    default=None,
    help="Discord guild ID to scrape (default: GUILD_ID from .env)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("./archive.db"),
    help="Output database file path",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
def scrape(
    guild_id: int | None,
    output: Path,
    verbose: bool,
) -> None:
    """Scrape a Discord server and save to database."""
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as e:
        click.echo(
            f"Error: Failed to load settings: {e}\n"
            "Ensure DISCORD_BOT_TOKEN is set in .env or environment.",
            err=True,
        )
        sys.exit(1)

    if guild_id is None:
        guild_id = settings.guild_id
    if guild_id is None:
        click.echo(
            "Error: --guild-id is required (or set GUILD_ID in .env).",
            err=True,
        )
        sys.exit(1)

    token = settings.discord_bot_token

    # Validate output path — resolve and ensure parent exists, reject traversal
    output = output.resolve()
    if not output.parent.exists():
        click.echo(f"Error: Output directory does not exist: {output.parent}", err=True)
        sys.exit(1)
    if not output.suffix:
        output = output.with_suffix(".db")

    # Setup database
    db_url = f"sqlite+aiosqlite:///{output.absolute()}"
    database = Database(db_url)

    async def run_scraper() -> int:
        """Run scraper and return exit code (0=success, 1=errors)."""
        await database.connect()
        await database.create_tables()

        bot = ArchiverBot(token, database)

        def progress_callback(channel_name: str, message_count: int) -> None:
            if verbose:
                click.echo(f"  {channel_name}: {message_count} messages...")

        try:
            click.echo("Connecting to Discord...")
            await bot.start()

            click.echo(f"Scraping guild {guild_id}...")
            stats = await bot.scrape_guild(guild_id, progress_callback)

            click.echo("\nScraping complete!")
            click.echo(f"  Guild: {stats['guild_name']}")
            click.echo(f"  Channels scraped: {stats['channels_scraped']}")
            click.echo(f"  Messages scraped: {stats['messages_scraped']}")
            click.echo(f"  Attachments found: {stats['attachments_found']}")

            if stats["errors"]:
                scrape_errors = cast(list[str], stats["errors"])
                click.echo(f"\nErrors ({len(scrape_errors)}):")
                for error in scrape_errors:
                    click.echo(f"  - {error}", err=True)
                return 1

            return 0

        finally:
            await bot.close()
            await database.disconnect()

    try:
        exit_code = asyncio.run(run_scraper())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        click.echo("\nScraping interrupted by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument(
    "database",
    type=click.Path(path_type=Path),
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8000,
    help="Port to serve on",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind to",
)
@click.option(
    "--attachments-dir",
    "-a",
    type=click.Path(path_type=Path),
    default=Path("./attachments"),
    help="Path to downloaded attachments directory",
)
@click.option(
    "--build-portal",
    is_flag=True,
    help="Build the SvelteKit portal before starting (requires npm)",
)
@click.option(
    "--postgres-url",
    default=None,
    help="PostgreSQL connection URL (e.g. postgresql+asyncpg://user:pass@host/db)",
)
def serve(
    database: Path,
    port: int,
    host: str,
    attachments_dir: Path,
    build_portal: bool,
    postgres_url: str | None,
) -> None:
    """Start the exploration portal (production mode).

    Serves the API and the pre-built SvelteKit portal as static files.
    Use --build-portal to automatically build the frontend first.
    """
    import uvicorn

    from wumpus_archiver.api.app import create_app
    from wumpus_archiver.storage.database import Database as DB

    if build_portal:
        _build_portal_static()

    db_path = database.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+aiosqlite:///{db_path}"
    db = DB(db_url)

    att_resolved = attachments_dir.resolve()
    att_resolved.mkdir(parents=True, exist_ok=True)
    att_path = att_resolved

    # Resolve postgres_url from settings if not provided
    pg_url = postgres_url
    if not pg_url:
        try:
            settings = Settings()  # type: ignore[call-arg]
            pg_url = settings.postgres_url
        except Exception:
            pass

    app = create_app(db, attachments_path=att_path, postgres_url=pg_url)

    click.echo(f"Starting portal at http://{host}:{port}")
    click.echo(f"Database: {db_path}")
    if att_path:
        click.echo(f"Attachments: {att_path}")
    else:
        click.echo("Attachments: not found (images served from Discord CDN)")
    if pg_url:
        click.echo("PostgreSQL: configured")
    uvicorn.run(app, host=host, port=port, limit_max_request_size=1_048_576)


def _build_portal_static() -> None:
    """Build the SvelteKit portal into static files.

    Raises:
        SystemExit: If npm is not found or the build fails.
    """
    import subprocess

    from wumpus_archiver.utils.process_manager import find_npm, resolve_portal_dir

    try:
        npm = find_npm()
        portal_dir = resolve_portal_dir()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Install dependencies if needed
    node_modules = portal_dir / "node_modules"
    if not node_modules.exists():
        click.echo("Installing portal dependencies...")
        result = subprocess.run(
            [npm, "install"],
            cwd=str(portal_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            click.echo(f"Error installing portal dependencies:\n{result.stderr}", err=True)
            sys.exit(1)

    click.echo("Building portal...")
    result = subprocess.run(
        [npm, "run", "build"],
        cwd=str(portal_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(f"Portal build failed:\n{result.stderr}\n{result.stdout}", err=True)
        sys.exit(1)

    click.echo("Portal built successfully.")


@cli.command()
@click.argument(
    "database",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--guild-id",
    type=int,
    default=None,
    help="Only download images for this guild (default: GUILD_ID from .env)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("./attachments"),
    help="Output directory for downloaded images",
)
@click.option(
    "--concurrency",
    "-c",
    type=int,
    default=5,
    help="Max concurrent downloads",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
def download(
    database: Path,
    guild_id: int | None,
    output: Path,
    concurrency: int,
    verbose: bool,
) -> None:
    """Download all image attachments from the archive to local storage."""
    import logging

    from wumpus_archiver.utils.downloader import ImageDownloader

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    db_path = database.resolve()
    db_url = f"sqlite+aiosqlite:///{db_path}"
    db = Database(db_url)

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    # Resolve guild_id before the async function to avoid scope issues
    resolved_guild_id = guild_id
    if resolved_guild_id is None:
        try:
            resolved_guild_id = Settings().guild_id  # type: ignore[call-arg]
        except Exception:
            pass

    click.echo(f"Database: {db_path}")
    click.echo(f"Output:   {output}")
    click.echo(f"Concurrency: {concurrency}")
    click.echo()

    async def run_download() -> int:
        """Run the image downloader."""
        await db.connect()

        downloader = ImageDownloader(
            database=db,
            output_dir=output,
            concurrency=concurrency,
        )

        def progress(channel_name: str, done: int, total: int) -> None:
            click.echo(f"  #{channel_name}: {done}/{total} processed")

        try:
            if resolved_guild_id:
                click.echo(f"Downloading images for guild {resolved_guild_id}...")
                stats = await downloader.download_guild_images(resolved_guild_id, progress)
            else:
                click.echo("Downloading all images...")
                stats = await downloader.download_all_images(progress)

            click.echo()
            click.echo("Download complete!")
            click.echo(f"  Total:          {stats.total}")
            click.echo(f"  Downloaded:     {stats.downloaded}")
            click.echo(f"  Already cached: {stats.already_exists}")
            click.echo(f"  Skipped (404):  {stats.skipped}")
            click.echo(f"  Failed:         {stats.failed}")
            click.echo(f"  Total size:     {stats.total_bytes / 1024 / 1024:.1f} MB")

            if stats.errors:
                click.echo(f"\nErrors ({len(stats.errors)}):")
                for error in stats.errors[:20]:
                    click.echo(f"  - {error}", err=True)
                return 1
            return 0

        finally:
            await db.disconnect()

    try:
        exit_code = asyncio.run(run_download())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        click.echo("\nDownload interrupted by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument(
    "database",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--guild-id",
    type=int,
    default=None,
    help="Guild ID to update (default: GUILD_ID from .env)",
)
def update(
    database: Path,
    guild_id: int | None,
) -> None:
    """Update an existing archive with new messages. (Not yet implemented)"""
    click.echo("Error: The 'update' command is not yet implemented (Phase 2).", err=True)
    sys.exit(2)


@cli.command()
@click.argument(
    "database",
    type=click.Path(path_type=Path),
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8000,
    help="Backend API port",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Backend host to bind to",
)
@click.option(
    "--frontend-port",
    type=int,
    default=5173,
    help="Vite dev server port",
)
@click.option(
    "--attachments-dir",
    "-a",
    type=click.Path(path_type=Path),
    default=Path("./attachments"),
    help="Path to downloaded attachments directory",
)
@click.option(
    "--postgres-url",
    default=None,
    help="PostgreSQL connection URL (e.g. postgresql+asyncpg://user:pass@host/db)",
)
def dev(
    database: Path,
    port: int,
    host: str,
    frontend_port: int,
    attachments_dir: Path,
    postgres_url: str | None,
) -> None:
    """Start development environment (backend + frontend with hot-reload)."""
    from wumpus_archiver.utils.process_manager import (
        ManagedProcess,
        find_npm,
        resolve_portal_dir,
        run_concurrently,
    )

    # Resolve paths
    db_path = database.resolve()
    att_dir = attachments_dir.resolve()
    att_dir.mkdir(parents=True, exist_ok=True)

    pg_url = postgres_url
    if not pg_url:
        try:
            settings = Settings()  # type: ignore[call-arg]
            pg_url = settings.postgres_url
        except Exception:
            pass

    # Find npm and portal directory
    try:
        npm = find_npm()
        portal_dir = resolve_portal_dir()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Check that portal dependencies are installed
    node_modules = portal_dir / "node_modules"
    if not node_modules.exists():
        click.echo("Installing portal dependencies...")
        import subprocess

        result = subprocess.run(
            [npm, "install"],
            cwd=str(portal_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            click.echo(f"Error installing dependencies: {result.stderr}", err=True)
            sys.exit(1)

    # Build CLI args for the backend
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "wumpus_archiver.api._dev_app:app",
        "--host", host,
        "--port", str(port),
        "--reload",
        "--reload-dir", "src",
    ]

    # Build Vite dev server command
    frontend_cmd = [npm, "run", "dev", "--", "--port", str(frontend_port)]

    # Create a thin app module for uvicorn --reload
    # We need a module-level app instance for uvicorn to reload
    _write_dev_app_module(db_path, att_dir, pg_url)

    processes = [
        ManagedProcess(
            label="backend",
            cmd=backend_cmd,
            cwd=Path.cwd(),
        ),
        ManagedProcess(
            label="frontend",
            cmd=frontend_cmd,
            cwd=portal_dir,
        ),
    ]

    click.echo("Starting development environment...")
    click.echo(f"  Backend:  http://{host}:{port} (API + uvicorn reload)")
    click.echo(f"  Frontend: http://localhost:{frontend_port} (Vite HMR)")
    click.echo(f"  Database: {db_path}")
    if att_dir:
        click.echo(f"  Attachments: {att_dir}")
    if pg_url:
        click.echo("  PostgreSQL: configured")
    click.echo("\nPress Ctrl+C to stop both servers.\n")

    try:
        exit_code = asyncio.run(run_concurrently(processes, stop_on_first_exit=True))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        click.echo("\nDevelopment servers stopped.")
        sys.exit(0)


def _write_dev_app_module(db_path: Path, attachments_path: Path | None, postgres_url: str | None = None) -> None:
    """Write a temporary module that uvicorn can import for --reload.

    Creates src/wumpus_archiver/api/_dev_app.py with a module-level `app`
    instance configured for the given database.

    Args:
        db_path: Resolved path to the SQLite database.
        attachments_path: Resolved path to attachments directory, or None.
        postgres_url: Optional PostgreSQL connection URL.
    """
    dev_module = Path(__file__).parent / "api" / "_dev_app.py"
    att_line = f'    attachments_path=Path("{attachments_path}"),' if attachments_path else ""
    pg_line = f'    postgres_url="{postgres_url}",' if postgres_url else ""
    content = f'''"""Auto-generated dev app instance for uvicorn --reload. DO NOT EDIT."""

from pathlib import Path

from wumpus_archiver.api.app import create_app
from wumpus_archiver.storage.database import Database

_db = Database("sqlite+aiosqlite:///{db_path}")
app = create_app(
    _db,
{att_line}
{pg_line}
)
'''
    dev_module.write_text(content)


@cli.command("mcp")
@click.argument(
    "database",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--http",
    "transport",
    flag_value="streamable-http",
    default=False,
    help="Run as HTTP server instead of stdio",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=9100,
    help="HTTP server port (only used with --http)",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="HTTP server host (only used with --http)",
)
@click.option(
    "--attachments-dir",
    "-a",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to downloaded attachments directory",
)
def mcp_command(
    database: Path,
    transport: str | bool,
    port: int,
    host: str,
    attachments_dir: Path | None,
) -> None:
    """Start the MCP server for AI agent integration.

    Runs in stdio mode (default) for Claude Desktop / Copilot, or
    use --http for network-accessible HTTP transport.
    """
    import logging

    from wumpus_archiver.mcp.server import create_mcp_server

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    db_path = database.resolve()
    att_path = attachments_dir.resolve() if attachments_dir else None

    # Try to load Discord token from settings
    discord_token: str | None = None
    try:
        settings = Settings()  # type: ignore[call-arg]
        discord_token = settings.discord_bot_token
    except Exception:
        pass

    server = create_mcp_server(
        db_path=db_path,
        attachments_path=att_path,
        discord_token=discord_token,
    )

    if transport:
        click.echo(f"Starting MCP server (HTTP) at http://{host}:{port}")
        click.echo(f"Database: {db_path}")
        server.run(transport="streamable-http", host=host, port=port)
    else:
        # stdio mode — no echo, just run
        server.run(transport="stdio")


@cli.command()
def init() -> None:
    """Initialize a new wumpus-archiver project."""
    click.echo("Initializing wumpus-archiver project...")

    # Create directories
    Path("./attachments").mkdir(exist_ok=True)
    Path("./logs").mkdir(exist_ok=True)

    # Create .env file if it doesn't exist
    env_file = Path(".env")
    if not env_file.exists():
        env_file.write_text("""# Discord Bot Configuration
DISCORD_BOT_TOKEN=your_bot_token_here

# Database Configuration
DATABASE_URL=sqlite+aiosqlite:///./wumpus_archive.db

# API Configuration
API_HOST=127.0.0.1
API_PORT=8000
API_DEBUG=false

# Scraper Configuration
BATCH_SIZE=1000
RATE_LIMIT_DELAY=0.5
MAX_RETRIES=5
DOWNLOAD_ATTACHMENTS=true
ATTACHMENTS_PATH=./attachments

# Portal Configuration
PORTAL_TITLE=Wumpus Archiver
PORTAL_DESCRIPTION=Discord Server Archive
DEFAULT_PAGE_SIZE=50

# Logging
LOG_LEVEL=INFO
""")
        click.echo("Created .env file - please edit with your Discord bot token")
    else:
        click.echo(".env file already exists")

    click.echo("\nProject initialized!")
    click.echo("Next steps:")
    click.echo("  1. Edit .env with your Discord bot token")
    click.echo("  2. Run: wumpus-archiver scrape --guild-id <GUILD_ID>")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
