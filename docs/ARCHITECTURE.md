# Wumpus Archiver — Architecture

## System Overview

Three-layer async system: **Discord Bot** (scraper) → **Storage** (SQLAlchemy + SQLite/PG) → **Web Portal** (FastAPI + SvelteKit).

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────────────────┐
│  Discord Bot │────▶│  Storage Layer   │────▶│  Web Portal                  │
│  (discord.py)│     │  (SQLite / PG)   │     │  FastAPI (API) + SvelteKit   │
└──────────────┘     └──────────────────┘     └──────────────────────────────┘
       ↑                    ↑↓                       ↑
  Discord API    Repositories (write)          Browser
                Archive reads (read)
```

## Component Breakdown

### 1. Models (`src/wumpus_archiver/models/`)

SQLAlchemy 2.0 declarative models with `Mapped[]` / `mapped_column()`.

| Model | PK | Key Fields |
|---|---|---|
| `Guild` | `BigInteger` (snowflake) | name, icon_url, owner_id, member_count, scrape_count |
| `Channel` | `BigInteger` | guild_id (FK), name, type, topic, position |
| `User` | `BigInteger` | username, discriminator, display_name, avatar_url, bot flag |
| `Message` | `BigInteger` | channel_id (FK), author_id (FK), content, embeds, timestamp |
| `Attachment` | `BigInteger` | message_id (FK), filename, url, content_type, size |
| `Reaction` | composite | message_id (FK), emoji, count |

- Base class in `base.py` with `TimestampMixin` (created_at / updated_at)
- Discord snowflake IDs as `BigInteger` primary keys
- String-based relationship targets with `cascade="all, delete-orphan"`

### 2. Storage Layer (`src/wumpus_archiver/storage/`)

**Database** (`database.py`):
- `connect()` / `disconnect()` / `create_tables()` lifecycle
- `session()` is `@asynccontextmanager` with auto-commit/rollback
- Async engine via `create_async_engine()`

**Repositories** (`repositories.py`) — the write side, used by the scraper:
- One standalone class per entity (no base class)
- Takes `AsyncSession` in `__init__`
- Core pattern: `upsert()` — check existence via `get_by_id()`, update or add
- Uses SQLAlchemy `select()` statement API

```python
class MessageRepository:
    def __init__(self, session: AsyncSession) -> None: ...
    async def upsert(self, message: Message) -> Message: ...
    async def get_by_id(self, message_id: int) -> Message | None: ...
    async def bulk_upsert(self, messages: list[Message]) -> list[Message]: ...
```

**Archive reads** (`archive_reads.py`) — the read side, used by the API routes (ADR 0002, ADR 0003):
- Plain async functions that take the `AsyncSession` the route opened and never write,
  commit, flush or close it. The module imports the models only, never FastAPI or the schemas
- A `Scope(guild, channel, author)` picks the part of the archive a read covers; all three
  apply together (a channel outside the guild yields nothing) and an empty scope is the
  whole archive
- Paged reads return `Page(rows, total, has_more, oldest_id, newest_id)`. One private helper
  over-fetches one row for `has_more` and computes `total` with `count(*)` from the same
  predicates as the rows, skipping the COUNT when the first page is the whole result
- Message cursors are anchored: `before` / `after` return the page adjacent to that message,
  as a `(created_at, id)` keyset, in the `Order` the caller requires. The channel messages
  route keeps oldest-first in one `DEFAULT_ORDER` constant until the portal flips
- Every ORDER BY carries a primary-key (or group-key) tie-break; aware datetimes are
  normalised to naive UTC; activity groups by day with `extract` and folds in Python, so
  every statement compiles for sqlite and postgresql (only SQLite is promised)
- `MediaKind` owns the image, GIF and video content types; `escape_like` is the one LIKE
  escaping helper

| Read | Serves |
|---|---|
| `messages(scope, order, limit, before, after, text, has, since, until, with_channel)` | Channel messages, search, a profile's recent messages |
| `attachments(scope, kind, limit, offset)` | Channel gallery, guild gallery, gallery timeline |
| `authors(scope, sort, limit, offset, name)` | People screen, top users |
| `summary(scope)`, `message_total(scope)`, `attachment_total(scope)`, `reaction_total(scope)` | Profile and guild totals, one statement each |
| `activity(scope, period, since)` | Monthly (or weekly) activity |
| `reactions(scope, limit)`, `channel_activity(scope, limit)` | Profile top reactions and channels |
| `guilds()`, `guild(id)`, `guild_channels(id)`, `guild_counts(ids)` | Guild list, detail and channels (two COUNTs for any number of guilds) |
| `top_channels(guild_id, limit)` | Overview's busiest channels, ranked by the ingest's `Channel.message_count` |
| `user(id)` | User detail and profile |

Out of scope: the GIF routes' raw SQL over `gif_index` (keeps its own LIKE escaping until
the GIF index has an owner) and the download stats' own grouped query.

### 3. Discord Bot (`src/wumpus_archiver/bot/scraper.py`)

- `ArchiverBot` wraps `commands.Bot` (composition, not inheritance)
- `scrape_guild()` is the main entry point
- Iterates `guild.text_channels`, fetches history with pagination
- Saves guilds, channels, users, messages, attachments, reactions
- Progress callback support for CLI output
- Rate limiting relies on discord.py's built-in handler

### 4. API Layer (`src/wumpus_archiver/api/`)

**App factory** (`app.py`):
- `create_app(database, *, attachments_dir=None, portal_build=None, scrape=None,
  api_auth_token=None, cors_origins=())` → `FastAPI`
- A pure function of its arguments: reads nothing from the environment, `.env`, the
  working directory or the package location. `serve` and the generated dev module resolve
  those through `wumpus_archiver/compose.py`: `serve_config` loads the bot token, API token
  and CORS origins in one `ServeSettings` load and raises on any invalid setting (startup
  fails closed), `scrape_control` turns the bot token into scrape control, and
  `portal_build_dir` finds the build
- Lifespan: connects the database only if it is not already connected and disconnects only
  what it connected (ADR 0001), so one factory call serves uvicorn and the test fixtures
- CORS allows only the `cors_origins` handed in (none by default; `serve` passes
  `CORS_ORIGINS` or its defaults), with no credentials, `GET`/`POST`/`OPTIONS` and the
  `Authorization` and `Content-Type` headers
- `POST /api/scrape/start` and `/api/scrape/cancel` require `Authorization: Bearer
  <api_auth_token>` (`auth.py`); with no token handed in they return 403, failing closed
- Mounts the attachments dir at `/attachments` when given; a missing directory raises
- Serves the portal build as an SPA when given (`index.html` fallback); `None` means API only

**Dependencies** (`deps.py`):
- Handlers declare `Db`, `AttachmentsDir`, `Scrape` or `ApiAuthToken` instead of reading
  `request.app.state`; the API token is held as a `SecretStr`, so no repr shows it
- `Wiring` is bound once by `create_app` and read back with `wiring_of(app)`;
  an app not built by the factory fails with `NotWiredError`

**Scrape control** (`scrape_control.py`):
- `ScrapeControl` protocol (`configured`, `is_busy`, `current_job`, `history`,
  `start_scrape`, `cancel`) plus the job models; imports pydantic only
- `ReadOnlyScrape`: the adapter used when no bot token is configured;
  `has_token` and the 400 on `/scrape/start` both come from `configured`

**Schemas** (`schemas.py`):
- Pydantic response models for all endpoints
- ~348 lines of typed response definitions

**Scrape Manager** (`scrape_manager.py`):
- Production adapter of `ScrapeControl`; owns the bot token (`ScrapeJobManager(database, token)`)
- Background scrape job tracking (start/cancel/status/history)
- Runs ArchiverBot in an asyncio task; imports discord.py lazily when a job starts

**Routes** (`routes/` — 9 domain modules):

| Module | Endpoints | Description |
|---|---|---|
| `guilds.py` | `GET /guilds`, `GET /guilds/{id}` | Guild listing and detail |
| `channels.py` | `GET /guilds/{id}/channels` | Channel list for a guild |
| `messages.py` | `GET /channels/{id}/messages` | Paginated messages |
| `search.py` | `GET /search` | Full-text message search |
| `gallery.py` | `GET /channels/{id}/gallery`, `GET /guilds/{id}/gallery`, `GET /guilds/{id}/gallery/timeline` | Image galleries |
| `stats.py` | `GET /guilds/{id}/stats` | Guild statistics |
| `users.py` | `GET /guilds/{id}/users`, `GET /users/{id}/profile` | User directory and profiles |
| `scrape.py` | `GET /scrape/status`, `POST /scrape/start`, `POST /scrape/cancel`, `GET /scrape/history` | Scrape control |
| `downloads.py` | `GET /downloads/stats` | Local attachment download stats |
| `gifs.py` | `GET /gifs`, `GET /gifs/random` | GIF index (raw SQL over `gif_index`) |
| `_helpers.py` | *(shared)* | `local_attachment_url()`, `rewrite_attachment_url()`, gallery helpers |

Read routes call archive reads and compose no query of their own; they only turn rows into
schemas (attachment URL rewriting, display names, page-local timeline grouping).

### 5. Web Portal (`portal/`)

SvelteKit 2 with adapter-static — builds to `portal/build/` as a pure SPA.

**Key libraries**: Svelte 5, TypeScript, Vite 7

**Architecture**:
- `lib/api.ts` — typed fetch wrapper with all API functions
- `lib/types.ts` — TypeScript interfaces matching backend schemas
- `lib/components/` — reusable components (MessageCard, GalleryGrid, etc.)
- `routes/` — page components (dashboard, channels, gallery, search, users, control)

**Development**: Vite dev server on `:5173` proxies `/api` to FastAPI on `:8000`.
**Production**: FastAPI serves pre-built static files from `portal/build/`.

### 6. CLI (`src/wumpus_archiver/cli.py`)

Click-based with 6 subcommands:

| Command | Description |
|---|---|
| `scrape` | Scrape a Discord server into SQLite |
| `serve` | Start production server (API + built SPA) |
| `dev` | Start dev environment (backend + frontend, hot-reload) |
| `download` | Download image attachments locally |
| `init` | Initialize project (`.env`, directories) |
| `update` | Update archive *(stub — not yet implemented)* |

### 7. Utilities (`src/wumpus_archiver/utils/`)

- `downloader.py` — `ImageDownloader` for concurrent attachment downloads
- `process_manager.py` — Async subprocess runner for `dev` command (runs uvicorn + Vite concurrently with colored output and graceful shutdown)

### 8. Configuration (`src/wumpus_archiver/config.py`)

- Pydantic-settings `BaseSettings` with `.env` support
- `Field(validation_alias="ENV_VAR_NAME")` pattern
- `@lru_cache` singleton via `get_settings()`
- Validators for port range, batch size, page size, etc.
- `GUILD_ID` (optional) — target server ID, used as default for `--guild-id` in CLI commands

## Data Flow

### Scraping Flow
```
1. CLI: wumpus-archiver scrape [--guild-id ID]  (defaults to GUILD_ID from .env)
2. ArchiverBot connects to Discord
3. Fetches guild metadata → GuildRepository.upsert()
4. For each text channel:
   a. Fetch message history (paginated, 100/request)
   b. For each message batch:
      - Save User, Message, Attachments, Reactions via repositories
   c. Progress callback to CLI
5. Report statistics and disconnect
```

### Portal Query Flow (Production)
```
1. Browser requests /channels → FastAPI serves index.html
2. SvelteKit SPA loads, JS fetches /api/guilds
3. API route handler opens an AsyncSession → archive reads → SQLite
4. JSON response → SvelteKit renders UI
```

### Portal Query Flow (Development)
```
1. Browser requests http://localhost:5173/channels
2. Vite dev server serves SvelteKit page (HMR)
3. SvelteKit JS fetches /api/guilds
4. Vite proxy forwards to http://127.0.0.1:8000/api/guilds
5. FastAPI handles as normal
```

## Scalability Considerations

| Scale | Messages | Storage | Approach |
|-------|----------|---------|----------|
| Small | <100K | <1GB | SQLite + SQL LIKE search |
| Medium | 100K-1M | 1-10GB | SQLite + FTS5 |
| Large | 1M-10M | 10-100GB | PostgreSQL + dedicated search |

## Deployment Options

### Option 1: Single Process (Current)
```bash
wumpus-archiver serve archive.db --build-portal -a ./attachments
```
FastAPI serves API + SPA + attachments on one port. Simplest setup.

### Option 2: Reverse Proxy
Nginx/Caddy in front for TLS, caching, and static file serving.

### Option 3: Docker Compose
- FastAPI container
- PostgreSQL container (optional, for scale)
- Nginx for static files + TLS
