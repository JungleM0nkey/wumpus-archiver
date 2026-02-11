# Wumpus Archiver

Self-hosted Discord server archival with a web exploration portal.

Scrape messages, channels, users, and attachments into a SQLite database, then browse everything through a SvelteKit UI served by FastAPI.

## Quick Start

```bash
pip install -e ".[dev]"
cp .env.example .env          # set DISCORD_BOT_TOKEN
```

Your Discord bot needs **Message Content** and **Server Members** privileged intents, plus Read Messages and Read Message History permissions.

```bash
# Scrape a server
wumpus-archiver scrape --guild-id 123456789

# Download image attachments locally
wumpus-archiver download ./archive.db

# Start the portal
wumpus-archiver serve ./archive.db --attachments-dir ./attachments
```

## Tech Stack

Python 3.12 · discord.py · FastAPI · SQLAlchemy 2.0 (async) · SvelteKit · SQLite

## Development

```bash
black src/ tests/ && ruff check src/ tests/ && mypy src/
pytest --cov=src/wumpus_archiver
cd portal && npm run dev       # frontend hot-reload
```

## License

MIT
