# Wumpus Archiver - AI Assistant Context

## Project Overview

Wumpus Archiver is a Discord server archival system with a web exploration portal. It scrapes Discord server history and provides a web interface for browsing archives.

**Current State**: Phases 1–3 complete — Core scraper, API layer, and SvelteKit portal all implemented and working. Phase 4 (advanced features) partially done (search, gallery, downloads).

> See also: `.github/copilot-instructions.md` for concise coding guidelines shared across AI agents.

## Project Structure

```
wumpus-archiver/
├── src/wumpus_archiver/       # Python backend (~4,400 lines)
│   ├── __init__.py
│   ├── cli.py                 # Click CLI (scrape, serve, dev, download, init, update)
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
│   │   └── scraper.py         # ArchiverBot with guild scraping
│   ├── storage/               # Repository pattern
│   │   ├── database.py        # Async engine + session management
│   │   └── repositories.py    # Per-entity repositories
│   ├── api/                   # FastAPI application
│   │   ├── app.py             # App factory (lifespan, CORS, SPA serving)
│   │   ├── schemas.py         # Pydantic response models
│   │   ├── scrape_manager.py  # Background scrape job manager
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
│   │       └── downloads.py   # GET /downloads/stats
│   └── utils/                 # Utilities
│       ├── downloader.py      # Image attachment downloader
│       └── process_manager.py # Concurrent process runner (dev command)
├── portal/                    # SvelteKit frontend (~6,400 lines)
│   └── src/
│       ├── lib/
│       │   ├── api.ts         # Typed API client
│       │   ├── types.ts       # TypeScript interfaces
│       │   └── components/    # Svelte 5 components
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
│           ├── channel/[id]/         # Message browser + gallery
│           ├── gallery/              # Guild-wide gallery
│           ├── timeline/             # Timeline media feed
│           ├── search/               # Full-text search
│           ├── users/ + users/[id]/  # User directory + profiles
│           └── control/              # Scrape control panel
├── tests/                     # pytest test suite (~1,060 lines)
├── docs/                      # Architecture & planning docs
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
- Domain-split route modules (9 files under `api/routes/`)
- SPA served by FastAPI in production (adapter-static builds to `portal/build/`)
- Vite dev server with API proxy in development
- Concurrent process manager for unified `dev` command

### Scope Decisions
- **NO Firecrawl integration** — removed from roadmap
- **NO MCP integration for core scraper** — using discord.py directly
- Focus on core archival functionality first

## Implementation Status

### Phase 1: Core Scraper ✅ COMPLETE
- [x] SQLAlchemy 2.0 models (Guild, Channel, User, Message, Attachment, Reaction)
- [x] Database layer with async support
- [x] Repository pattern (one class per entity, upsert semantics)
- [x] Discord bot scraper (ArchiverBot) with pagination
- [x] CLI interface (scrape, init commands)
- [x] Configuration management with Pydantic

### Phase 2: Storage & API ✅ COMPLETE
- [x] FastAPI application factory with lifespan management
- [x] REST API — 17 endpoints across 9 route modules
- [x] Pydantic response schemas
- [x] CORS configuration for development
- [x] Background scrape job manager (start/cancel from web UI)
- [x] Attachment download system with progress tracking

### Phase 3: Portal Foundation ✅ COMPLETE
- [x] SvelteKit project with adapter-static
- [x] Typed API client (`lib/api.ts`)
- [x] Dashboard with guild statistics
- [x] Channel list and message browser
- [x] Image gallery (per-channel and guild-wide)
- [x] Timeline-grouped media feed
- [x] Full-text search with filters
- [x] User directory and profile pages
- [x] Scrape control panel
- [x] Message card component (embeds, attachments, reactions)
- [x] Lightbox for image viewing
- [x] Navigation component

### Phase 3.5: DevOps & Tooling ✅ COMPLETE
- [x] Unified `dev` command (backend + frontend, hot-reload)
- [x] `serve --build-portal` for one-command production start
- [x] Concurrent process manager (`utils/process_manager.py`)
- [x] Makefile with all common targets
- [x] SPA fallback serving in production

### Phase 4: Advanced Features (PARTIAL)
- [x] Search (basic full-text via SQL LIKE)
- [x] Image gallery with timeline grouping
- [x] Attachment download management
- [ ] SQLite FTS5 virtual table for proper full-text search
- [ ] Analytics and visualizations (charts, heatmaps)
- [ ] Export formats (JSON, HTML, CSV)
- [ ] Incremental update (`update` command — stub only)
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
- `GuildRepository` — Guild CRUD and statistics
- `ChannelRepository` — Channel CRUD and listing
- `MessageRepository` — Message CRUD with pagination
- `UserRepository` — User CRUD and activity queries
- `AttachmentRepository` — Attachment tracking and queries
- `ReactionRepository` — Reaction aggregation

Each takes `AsyncSession` in `__init__`. Core pattern: `upsert()` checks existence via `get_by_id()`, updates or adds.

## Environment Variables

See `.env.example` for all options. Key variables:
- `DISCORD_BOT_TOKEN` — Required for Discord API access
- `GUILD_ID` — Target Discord server ID (default for `--guild-id` in CLI commands)
- `DATABASE_URL` — Database connection string
- `API_HOST` / `API_PORT` — API server binding
- `BATCH_SIZE` / `RATE_LIMIT_DELAY` — Scraping configuration
- `DOWNLOAD_ATTACHMENTS` / `ATTACHMENTS_PATH` — Attachment management
- `LOG_LEVEL` — Logging verbosity

## Known Issues / TODOs

1. `bulk_upsert` in repositories is sequential (loops `upsert()`), not true bulk
2. Embeds stored as `str()` not JSON — should use `json.dumps()`
3. Rate limiting relies on discord.py built-in handler; no custom header parsing
4. `update` command is a stub (not yet implemented)
5. No Alembic migrations — tables created via `create_tables()`
6. Search uses SQL LIKE — should migrate to FTS5 for performance
7. No export functionality yet

## Resources

- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
- [SvelteKit Documentation](https://svelte.dev/docs/kit/)
- [Click Documentation](https://click.palletsprojects.com/)
