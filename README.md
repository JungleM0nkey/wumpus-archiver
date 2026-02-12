# Wumpus Archiver

Self-hosted Discord server archival with a web exploration portal.

Scrape messages, channels, users, and attachments into a SQLite database, then browse everything through a SvelteKit UI served by FastAPI.

## Quick Start

```bash
pip install -e ".[dev]"
cd portal && npm install && cd ..
cp .env.example .env          # set DISCORD_BOT_TOKEN
```

Your Discord bot needs **Message Content** and **Server Members** privileged intents, plus Read Messages and Read Message History permissions.

```bash
# Scrape a server (uses GUILD_ID from .env, or pass --guild-id)
wumpus-archiver scrape
wumpus-archiver scrape --guild-id 123456789

# Download image attachments locally
wumpus-archiver download ./archive.db -v
```

## Running the App

### Development (hot-reload on both backend & frontend)

```bash
# Single command — starts FastAPI (uvicorn --reload) + Vite dev server
wumpus-archiver dev ./archive.db -a ./attachments

# Or using Make
make dev
```

Backend runs on `:8000`, frontend on `:5173` with Vite HMR and API proxy.
Press Ctrl+C to stop both.

### Production

```bash
# Build the portal then serve everything from one process
wumpus-archiver serve ./archive.db --build-portal -a ./attachments

# Or build and serve separately
cd portal && npm run build && cd ..
wumpus-archiver serve ./archive.db -a ./attachments

# Using Make
make serve-build   # build + serve
make serve         # serve only (portal must already be built)
```

## CLI Reference

| Command | Description |
|---|---|
| `wumpus-archiver init` | Initialize project (creates `.env`, directories) |
| `wumpus-archiver scrape` | Scrape a Discord server into SQLite (uses `GUILD_ID` from `.env`) |
| `wumpus-archiver download DB` | Download image attachments locally |
| `wumpus-archiver dev DB` | Start dev environment (backend + frontend, hot-reload) |
| `wumpus-archiver serve DB` | Start production server (API + built SPA) |
| `wumpus-archiver update DB` | Update archive with new messages *(not yet implemented)* |

All commands support `--help` for full options.

## Make Targets

Run `make help` for the full list. Highlights:

| Target | Description |
|---|---|
| `make install` | Install all dependencies (Python + Node) |
| `make dev` | Start dev environment (backend + frontend with hot-reload) |
| `make build` | Build the SvelteKit portal for production |
| `make serve` | Start production server (API + built portal) |
| `make serve-build` | Build portal then start production server |
| `make lint` | Run ruff + mypy + svelte-check |
| `make format` | Auto-format Python code (ruff + black) |
| `make test` | Run Python tests |
| `make test-cov` | Run tests with coverage report |
| `make clean` | Remove build artifacts and caches |

Override defaults with env vars: `DB=my.db PORT=9000 make dev`

## Project Structure

```
wumpus-archiver/
├── src/wumpus_archiver/       # Python backend
│   ├── cli.py                 # Click CLI (scrape, serve, dev, download, init)
│   ├── config.py              # Pydantic settings (.env support)
│   ├── models/                # SQLAlchemy 2.0 models (7 entities)
│   ├── storage/               # Database + repository layer
│   ├── bot/                   # Discord scraper (discord.py)
│   ├── api/                   # FastAPI app + route handlers
│   │   ├── app.py             # App factory with SPA serving
│   │   ├── schemas.py         # Pydantic response schemas
│   │   ├── scrape_manager.py  # Background scrape job manager
│   │   └── routes/            # Domain-split route modules (9 files)
│   └── utils/                 # Downloader, process manager
├── portal/                    # SvelteKit frontend (adapter-static)
│   └── src/
│       ├── lib/               # API client, components, types
│       └── routes/            # Pages (home, channels, gallery, search, etc.)
├── tests/                     # pytest test suite
├── docs/                      # Architecture & planning docs
├── Makefile                   # Convenience targets
└── pyproject.toml             # Project metadata & dependencies
```

## Tech Stack

- **Backend**: Python 3.12 · discord.py · FastAPI · SQLAlchemy 2.0 (async) · uvicorn
- **Database**: SQLite (aiosqlite) with optional PostgreSQL (asyncpg)
- **Frontend**: SvelteKit 2 · Svelte 5 · TypeScript · Vite
- **Quality**: ruff · black · mypy · pytest · svelte-check

## API Endpoints

All endpoints are under `/api/`:

| Endpoint | Description |
|---|---|
| `GET /guilds` | List archived guilds |
| `GET /guilds/{id}` | Guild detail |
| `GET /guilds/{id}/channels` | Channel list for a guild |
| `GET /guilds/{id}/stats` | Guild statistics |
| `GET /guilds/{id}/users` | Users in a guild |
| `GET /guilds/{id}/gallery` | Image gallery for a guild |
| `GET /guilds/{id}/gallery/timeline` | Timeline-grouped gallery |
| `GET /channels/{id}/messages` | Paginated messages |
| `GET /channels/{id}/gallery` | Channel image gallery |
| `GET /search` | Full-text message search |
| `GET /users/{id}/profile` | User profile with stats |
| `GET /downloads/stats` | Local attachment download stats |
| `GET /scrape/status` | Current scrape job status |
| `POST /scrape/start` | Start a scrape job |
| `POST /scrape/cancel` | Cancel running scrape |
| `GET /scrape/history` | Scrape job history |

## Portal Pages

| Route | Description |
|---|---|
| `/` | Dashboard with guild stats |
| `/channels` | Channel list with message counts |
| `/channel/[id]` | Message browser for a channel |
| `/channel/[id]/gallery` | Image gallery for a channel |
| `/gallery` | Guild-wide image gallery |
| `/timeline` | Timeline-grouped media feed |
| `/search` | Full-text search with filters |
| `/users` | User directory |
| `/users/[id]` | User profile page |
| `/control` | Scrape control panel |

## Environment Variables

See `.env.example` for all options. Key variables:

| Variable | Default | Description |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *(required)* | Discord bot token |
| `GUILD_ID` | *(none)* | Target Discord server ID (used as default for `--guild-id`) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./wumpus_archive.db` | Database connection |
| `API_HOST` | `127.0.0.1` | API bind host |
| `API_PORT` | `8000` | API bind port |
| `BATCH_SIZE` | `1000` | Messages per scrape batch |
| `RATE_LIMIT_DELAY` | `0.5` | Delay between API calls |
| `DOWNLOAD_ATTACHMENTS` | `true` | Auto-download attachments |
| `ATTACHMENTS_PATH` | `./attachments` | Local attachment storage |
| `LOG_LEVEL` | `INFO` | Logging level |

## Development

```bash
# Format + lint + type-check
make format && make lint

# Run tests
make test

# Run tests with coverage
make test-cov
```

## License

MIT
