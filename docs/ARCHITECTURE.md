# Wumpus Archiver — Architecture

## System Overview

Three-layer async system: **Discord Bot** (scraper) → **Storage** (SQLAlchemy + SQLite/PG) → **Web Portal** (FastAPI + SvelteKit).

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────────────────┐
│  Discord Bot │────▶│  Storage Layer   │────▶│  Web Portal                  │
│  (discord.py)│     │  (SQLite / PG)   │     │  FastAPI (API) + SvelteKit   │
└──────────────┘     └──────────────────┘     └──────────────────────────────┘
       ↑                    ↑↓                       ↑
  Discord API         Repositories              Browser
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

**Repositories** (`repositories.py`):
- One standalone class per entity (no base class)
- Takes `AsyncSession` in `__init__`
- Core pattern: `upsert()` — check existence via `get_by_id()`, update or add
- Uses SQLAlchemy `select()` statement API

```python
class MessageRepository:
    def __init__(self, session: AsyncSession) -> None: ...
    async def upsert(self, message: Message) -> Message: ...
    async def get_by_id(self, message_id: int) -> Message | None: ...
    async def get_by_channel(self, channel_id: int, limit: int, before: int | None) -> list[Message]: ...
    async def bulk_upsert(self, messages: list[Message]) -> int: ...
```

### 3. Discord Bot (`src/wumpus_archiver/bot/scraper.py`)

- `ArchiverBot` wraps `commands.Bot` (composition, not inheritance)
- `scrape_guild()` is the main entry point
- Iterates `guild.text_channels`, fetches history with pagination
- Saves guilds, channels, users, messages, attachments, reactions
- Progress callback support for CLI output
- Rate limiting relies on discord.py's built-in handler

### 4. API Layer (`src/wumpus_archiver/api/`)

**App factory** (`app.py`):
- `create_app(database, attachments_path, discord_token)` → `FastAPI`
- Lifespan: connects/disconnects database
- CORS for dev (localhost:5173, :3000, :8000)
- Mounts local attachments as static files
- SPA fallback: serves `portal/build/index.html` for unmatched routes

**Schemas** (`schemas.py`):
- Pydantic response models for all endpoints
- ~348 lines of typed response definitions

**Scrape Manager** (`scrape_manager.py`):
- Background scrape job tracking (start/cancel/status/history)
- Runs ArchiverBot in asyncio task
- ~220 lines

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
| `_helpers.py` | *(shared)* | `get_db()`, `rewrite_attachment_url()`, gallery helpers |

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
3. API route handler → AsyncSession → Repository → SQLite
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
