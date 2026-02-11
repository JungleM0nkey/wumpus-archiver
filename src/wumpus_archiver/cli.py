"""Command-line interface for wumpus-archiver."""

import asyncio
import sys
from pathlib import Path
from typing import cast

import click

from wumpus_archiver.bot.scraper import ArchiverBot
from wumpus_archiver.config import Settings
from wumpus_archiver.storage.database import Database


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """Wumpus Archiver - Discord server archival system."""
    pass


@cli.command()
@click.option(
    "--guild-id",
    type=int,
    required=True,
    help="Discord guild ID to scrape",
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
    guild_id: int,
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
    type=click.Path(exists=True, path_type=Path),
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
def serve(
    database: Path,
    port: int,
    host: str,
    attachments_dir: Path,
) -> None:
    """Start the exploration portal."""
    import uvicorn

    from wumpus_archiver.api.app import create_app
    from wumpus_archiver.storage.database import Database as DB

    db_path = database.resolve()
    db_url = f"sqlite+aiosqlite:///{db_path}"
    db = DB(db_url)

    att_path = attachments_dir.resolve() if attachments_dir.exists() else None
    app = create_app(db, attachments_path=att_path)

    click.echo(f"Starting portal at http://{host}:{port}")
    click.echo(f"Database: {db_path}")
    if att_path:
        click.echo(f"Attachments: {att_path}")
    else:
        click.echo("Attachments: not found (images served from Discord CDN)")
    uvicorn.run(app, host=host, port=port)


@cli.command()
@click.argument(
    "database",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--guild-id",
    type=int,
    default=None,
    help="Only download images for this guild",
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
            if guild_id:
                click.echo(f"Downloading images for guild {guild_id}...")
                stats = await downloader.download_guild_images(guild_id, progress)
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
    required=True,
    help="Guild ID to update",
)
def update(
    database: Path,
    guild_id: int,
) -> None:
    """Update an existing archive with new messages. (Not yet implemented)"""
    click.echo("Error: The 'update' command is not yet implemented (Phase 2).", err=True)
    sys.exit(2)


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
