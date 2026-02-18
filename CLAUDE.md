# Wumpus Archiver - AI Assistant Context

## Project Overview

Wumpus Archiver is a Discord server archival system with a web exploration portal. It scrapes Discord server history and provides a web interface for browsing archives.

**Current State**: Phases 1–4 largely complete — Core scraper with incremental updates, API layer with dual-database support (SQLite + PostgreSQL), SvelteKit portal, Docker deployment, CI/CD, and MCP server all implemented. Remaining: FTS5 search, analytics charts, export formats.

> See also: `.github/copilot-instructions.md` for concise coding guidelines shared across AI agents.

## Project Structure

```
wumpus-archiver/
├── src/wumpus_archiver/       # Python backend
│   ├── __init__.py
│   ├── cli.py                 # Click CLI (scrape, serve, dev, download, init, mcp)
│   ├── config.py              # Pydantic settings management
│   ├── models/                # SQLAlchemy 2.0 models
│   │   ├── base.py            # DeclarativeBase + TimestampMixin
│   │   ├── guild.py
│   │   ├── channel.py
│   │   ├── user.py
│   │   ├── message.py
│   │   ├── attachment.py
│   │   └── reaction.py
│   ├── bot/                   # Discord bot scraper
│   │   └── scraper.py         # ArchiverBot with incremental scraping
│   ├── storage/               # Repository pattern
│   │   ├── database.py        # Async engine + session + DatabaseRegistry
│   │   └── repositories.py    # Per-entity repositories
│   ├── api/                   # FastAPI application
│   │   ├── app.py             # App factory (lifespan, CORS, SPA serving)
│   │   ├── auth.py            # Bearer token auth middleware (API_SECRET)
│   │   ├── schemas.py         # Pydantic response models
│   │   ├── scrape_manager.py  # Background scrape job manager
│   │   ├── download_manager.py # Background image download job manager
│   │   ├── transfer_manager.py # SQLite→PostgreSQL data transfer
│   │   └── routes/            # Domain-split route modules
│   │       ├── __init__.py    # Router aggregation
│   │       ├── _helpers.py    # get_db(), URL rewriting, shared utils
│   │       ├── guilds.py      # GET /guilds, GET /guilds/{id}
│   │       ├── channels.py    # GET /guilds/{id}/channels
│   │       ├── messages.py    # GET /channels/{id}/messages
│   │       ├── search.py      # GET /search
│   │       ├── gallery.py     # Channel/guild gallery + timeline
│   │       ├── stats.py       # GET /guilds/{id}/stats
│   │       ├── users.py       # Users list + profile
│   │       ├── scrape.py      # Scrape control (start/cancel/status)
│   │       ├── downloads.py   # Download stats + background job (start/cancel/status)
│   │       ├── datasource.py  # GET/PUT /datasource (switch active DB)
│   │       └── transfer.py    # POST/GET /transfer (SQLite→PG migration)
│   ├── mcp/                   # MCP server (Model Context Protocol)
│   └── utils/                 # Utilities
│       ├── downloader.py      # Image attachment downloader
│       └── process_manager.py # Concurrent process runner (dev command)
├── portal/                    # SvelteKit frontend
│   └── src/
│       ├── lib/
│       │   ├── api.ts         # Typed API client
│       │   ├── types.ts       # TypeScript interfaces
│       │   └── components/    # Svelte 5 components
│       │       ├── ChannelGallery.svelte
│       │       ├── GalleryGrid.svelte
│       │       ├── Lightbox.svelte
│       │       ├── MessageCard.svelte
│       │       ├── Nav.svelte
│       │       ├── SearchBar.svelte
│       │       ├── StatCard.svelte
│       │       └── TimelineFeed.svelte
│       └── routes/            # SvelteKit pages
│           ├── +page.svelte          # Dashboard
│           ├── channels/             # Channel list
│           ├── channel/[id]/         # Message browser + gallery tab
│           ├── timeline/             # Timeline media feed
│           ├── search/               # Full-text search
│           ├── users/ + users/[id]/  # User directory + profiles
│           └── control/              # Scrape & data management panel
├── tests/                     # pytest test suite
├── docs/                      # Architecture & planning docs
├── Dockerfile                 # Multi-stage Docker build
├── docker-compose.yml         # Docker Compose with PostgreSQL
├── .github/workflows/         # CI/CD (lint, test, Docker publish)
├── Makefile                   # Convenience targets (make dev, make serve, etc.)
└── pyproject.toml             # Project metadata & dependencies
```

## Key Decisions

### Tech Stack
- **Backend**: Python 3.12, discord.py, FastAPI, SQLAlchemy 2.0, uvicorn
- **Database**: SQLite (default via aiosqlite), PostgreSQL (optional via asyncpg)
- **Frontend**: SvelteKit 2, Svelte 5, TypeScript, Vite 7, adapter-static
- **Quality**: ruff, black, mypy, pytest, svelte-check

### Architecture Patterns
- Repository pattern for database operations
- Async/await throughout (async engine, async sessions)
- Pydantic settings for configuration with `.env` support
- Click for CLI interface
- Domain-split route modules (11 files under `api/routes/`)
- `DatabaseRegistry` for multi-source database management (SQLite + PostgreSQL), with lazy-initialized `asyncio.Lock` for thread-safe runtime switching
- `TransferManager` for background SQLite→PostgreSQL data migration with idempotency logging
- `DownloadManager` for background image download jobs — holds `DatabaseRegistry` reference (not a snapshot) so datasource switches are reflected
- Bearer token authentication (`API_SECRET`) on all state-modifying endpoints (POST/PUT), using `hmac.compare_digest()` for timing-safe comparison
- Frontend API client (`api.ts`) injects `Authorization: Bearer` header automatically when a token is stored in `localStorage`
- SPA fallback with path traversal protection (resolved paths must stay within `portal/build/`)
- Incremental scraping via `last_message_id` cursor
- SPA served by FastAPI in production (adapter-static builds to `portal/build/`)
- Vite dev server with API proxy in development
- Concurrent process manager for unified `dev` command
- Docker multi-stage build with PostgreSQL via docker-compose; entrypoint script fixes bind-mount ownership then drops to non-root `archiver` user via `gosu`
- MCP server shares `ScrapeJobManager` and download task references via `AppContext` lifespan
- Dialect-aware SQL: `func.strftime` (SQLite) vs `func.to_char` (PostgreSQL) for date grouping queries

## Implementation Status

### Phase 1: Core Scraper ✅ COMPLETE
- [x] SQLAlchemy 2.0 models (Guild, Channel, User, Message, Attachment, Reaction)
- [x] Database layer with async support
- [x] Repository pattern (one class per entity, upsert semantics)
- [x] Discord bot scraper (ArchiverBot) with pagination
- [x] Incremental scraping (only fetches new messages via `last_message_id` cursor)
- [x] Per-reaction error isolation (flush/rollback/merge prevents one bad reaction from poisoning a batch)
- [x] CLI interface (scrape, init commands)
- [x] Configuration management with Pydantic

### Phase 2: Storage & API ✅ COMPLETE
- [x] FastAPI application factory with lifespan management
- [x] REST API — 22+ endpoints across 11 route modules
- [x] Pydantic response schemas
- [x] CORS configuration for development
- [x] Background scrape job manager (start/cancel from web UI)
- [x] Attachment download system with progress tracking (CLI + API trigger)
- [x] Dual database support: `DatabaseRegistry` for SQLite + PostgreSQL
- [x] Data source switching API (`GET/PUT /datasource`)
- [x] Background data transfer (`POST /transfer/start`, `GET /transfer/status`)
- [x] Automatic PostgreSQL sequence reset after data transfers

### Phase 3: Portal Foundation ✅ COMPLETE
- [x] SvelteKit project with adapter-static
- [x] Typed API client (`lib/api.ts`)
- [x] Dashboard with guild statistics
- [x] Channel list and message browser
- [x] Per-channel gallery tab (merged from standalone gallery page)
- [x] Timeline-grouped media feed
- [x] Full-text search with filters
- [x] User directory and profile pages
- [x] Scrape control panel with channel selector, real progress, and dynamic history refresh
- [x] Data source switcher and transfer controls in control panel
- [x] Image download management in Utilities drawer (start/cancel/progress)
- [x] Message card component (embeds, attachments, reactions)
- [x] Lightbox for image viewing
- [x] Navigation component

### Phase 3.5: DevOps & Tooling ✅ COMPLETE
- [x] Unified `dev` command (backend + frontend, hot-reload)
- [x] `serve --build-portal` for one-command production start
- [x] Concurrent process manager (`utils/process_manager.py`)
- [x] Makefile with all common targets
- [x] SPA fallback serving in production
- [x] Docker multi-stage build (`Dockerfile`)
- [x] Docker Compose with PostgreSQL (`docker-compose.yml`)
- [x] CI/CD workflows (lint/test on PR, Docker publish on tags)
- [x] MCP server for AI agent integration

### Phase 4: Advanced Features (PARTIAL)
- [x] Search (basic full-text via SQL LIKE)
- [x] Image gallery with timeline grouping
- [x] Attachment download management (CLI + web UI with background jobs)
- [x] Incremental scraping (re-scrape fetches only new messages)
- [x] Channel-level selective scraping (pick specific channels)
- [x] SQLite→PostgreSQL data transfer with progress UI
- [ ] SQLite FTS5 virtual table for proper full-text search
- [ ] Analytics and visualizations (charts, heatmaps)
- [ ] Export formats (JSON, HTML, CSV)
- [ ] Alembic migrations

## Development Workflow

### Starting development
```bash
# Install everything
make install

# Start both servers with hot-reload
make dev
# Or: wumpus-archiver dev ./archive.db -a ./attachments
```

### Production deployment
```bash
# Build portal and start server
make serve-build
# Or: wumpus-archiver serve ./archive.db --build-portal -a ./attachments

# Docker deployment (with PostgreSQL)
docker compose up -d
```

### Code quality
```bash
make format    # ruff + black
make lint      # ruff + mypy + svelte-check
make test      # pytest
make test-cov  # pytest + coverage
```

## Adding a New Feature

### Adding a Model
1. Create model in `src/wumpus_archiver/models/`
2. Re-export in `models/__init__.py`
3. Add repository class in `storage/repositories.py`
4. Re-export in `storage/__init__.py`

### Adding an API Endpoint
1. Add or edit route module in `api/routes/`
2. Add Pydantic schemas in `api/schemas.py`
3. Register router in `api/routes/__init__.py` (if new module)

### Adding a Portal Page
1. Create route directory in `portal/src/routes/`
2. Add API function in `portal/src/lib/api.ts`
3. Add types in `portal/src/lib/types.ts`

## Repository Pattern

All database access through standalone repositories:
- `GuildRepository` — Guild CRUD, statistics, scrape metadata tracking
- `ChannelRepository` — Channel CRUD, listing, `mark_scraped()`, message metadata
- `MessageRepository` — Message CRUD with pagination, bulk upsert
- `UserRepository` — User CRUD and activity queries
- `AttachmentRepository` — Attachment tracking and queries
- `ReactionRepository` — Reaction aggregation (composite lookup by message+emoji)

Each takes `AsyncSession` in `__init__`. Core pattern: `upsert()` checks existence via `get_by_id()`, updates or adds.

## Database Architecture

The app supports dual databases via `DatabaseRegistry`:
- **SQLite** (default) — single-file, zero-config, used for local development
- **PostgreSQL** (optional) — set `POSTGRES_URL` env var to enable

`DatabaseRegistry` manages named database sources and allows runtime switching between them (protected by a lazy-initialized `asyncio.Lock` for concurrent request safety — created on first use to avoid Python 3.12+ event loop issues). The active source is used for all API queries via `get_db(request)` in route handlers — never accessed through a stale `app.state.database` reference. `DownloadManager` holds a `DatabaseRegistry` reference and resolves the active database on each operation, so datasource switches are reflected immediately. A `TransferManager` handles background data migration from SQLite to PostgreSQL with per-table batch transfers, automatic sequence resets, and idempotency logging (inserted vs updated row counts).

### MCP Server Architecture

The MCP server (`mcp/server.py`) uses an `AppContext` dataclass in its lifespan to share state across tool invocations:
- `db: Database` — shared database connection
- `scrape_manager: ScrapeJobManager` — singleton, same instance used by all scrape tools
- `download_tasks: set[asyncio.Task]` — tracked background download tasks with done callbacks

This ensures MCP tools (scrape, cancel, status, download) operate on the same state rather than creating orphan instances.

## Authentication

State-modifying API endpoints (POST/PUT) are protected by Bearer token authentication via the `API_SECRET` environment variable.

- **If `API_SECRET` is not set**: All requests are allowed (development mode)
- **If `API_SECRET` is set**: All POST/PUT endpoints require `Authorization: Bearer <API_SECRET>` header
- **Protected endpoints**: `/api/scrape/*`, `/api/transfer/*`, `/api/datasource` (PUT), `/api/downloads/*` (POST)
- **Auth check endpoint**: `GET /api/auth/check` — returns `{authenticated, auth_required}` status
- **Timing-safe**: Secret comparison uses `hmac.compare_digest()` in both `auth.py` and the auth check endpoint

### Frontend Auth Flow

1. On app load, `+layout.svelte` restores any stored token from `localStorage('wumpus_api_token')`
2. Calls `GET /api/auth/check` to determine if auth is required
3. If auth is required and no token stored, prompts the user for the API secret
4. Token is stored in `localStorage` and injected into all `fetchJSON()` requests via `Authorization: Bearer` header
5. The `setApiToken()` / `getApiToken()` functions in `api.ts` manage the token lifecycle

```bash
# Test auth is working
curl -X POST http://localhost:8000/api/scrape/start \
  -H "Authorization: Bearer your_secret_here" \
  -H "Content-Type: application/json" \
  -d '{"guild_id": "123456789"}'

# Without token (should return 401 when API_SECRET is set)
curl -X POST http://localhost:8000/api/scrape/start
```

## Environment Variables

See `.env.example` for all options. Key variables:
- `DISCORD_BOT_TOKEN` — Required for Discord API access
- `GUILD_ID` — Target Discord server ID (default for `--guild-id` in CLI commands)
- `DATABASE_URL` — SQLite connection string (default: `sqlite+aiosqlite:///./wumpus_archive.db`)
- `POSTGRES_URL` — PostgreSQL connection string (optional, enables dual-database mode)
- `API_HOST` / `API_PORT` — API server binding
- `API_SECRET` — Bearer token for API authentication (optional; if unset, all requests allowed)
- `BATCH_SIZE` / `RATE_LIMIT_DELAY` — Scraping configuration
- `DOWNLOAD_ATTACHMENTS` / `ATTACHMENTS_PATH` — Attachment management
- `LOG_LEVEL` — Logging verbosity

## Security Notes

- Docker container runs as non-root `archiver` user (UID 1000); entrypoint script (`docker-entrypoint.sh`) runs as root only to fix bind-mount ownership, then drops privileges via `gosu`
- API authentication via `API_SECRET` Bearer token with `hmac.compare_digest()` (timing-safe) — see Authentication section
- SPA fallback (`app.py`) includes path traversal protection: resolved file paths must stay within `portal/build/`
- CORS restricted to `GET`, `POST`, `PUT`, `OPTIONS` methods and `Content-Type`, `Authorization` headers
- HTTP request size limited via `h11_max_incomplete_event_size=1_048_576` (1 MB) in uvicorn config
- All path parameters validated with `Path(gt=0)` to reject invalid IDs
- Pydantic `@field_validator` on `ScrapeStartRequest` validates snowflake ID format

## Known Issues / TODOs

1. `bulk_upsert` in repositories is sequential (loops `upsert()`), not true bulk
2. Embeds stored as `str()` not JSON — should use `json.dumps()`
3. Rate limiting relies on discord.py built-in handler; no custom header parsing
4. No Alembic migrations — tables created via `create_tables()`
5. Search uses SQL LIKE — should migrate to FTS5 for performance
6. No export functionality yet
7. `control/+page.svelte` is ~1,900 lines — should extract `ChannelSelector` component
8. No rate limiting on API endpoints
9. Pre-existing svelte-check TypeScript errors (24) in Nav.svelte, control page, and user pages

## Resources

- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
- [SvelteKit Documentation](https://svelte.dev/docs/kit/)
- [Click Documentation](https://click.palletsprojects.com/)
