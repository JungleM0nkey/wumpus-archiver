# Project Guidelines

## Code Style

- **Python 3.12+** — use `str | None` union syntax, `Mapped[]` type hints, full annotations on all signatures
- **Line length 100** — Black formats, Ruff lints (E, W, F, I, N, UP, B, C4, SIM rules)
- **Strict mypy** — `disallow_untyped_defs=true`; all functions must have type annotations
- **Google-style docstrings** with `Args:` / `Returns:` on public methods; one-liners on private methods
- **Absolute imports** everywhere: `from wumpus_archiver.models.guild import Guild` (no relative imports)
- `__init__.py` re-exports key symbols via `__all__`; use `TYPE_CHECKING` guard for circular relationship imports

Exemplary files: [models/guild.py](src/wumpus_archiver/models/guild.py), [storage/repositories.py](src/wumpus_archiver/storage/repositories.py)

## Architecture

Three-layer async system: **Discord Bot** (scraper) → **Storage** (SQLAlchemy + SQLite/PG) → **Web Portal** (FastAPI + SvelteKit).

- **Models** (`src/wumpus_archiver/models/`): SQLAlchemy 2.0 declarative with `Mapped[]`/`mapped_column()`. Discord snowflake IDs as `BigInteger` PKs. String-based relationship targets with `cascade="all, delete-orphan"`.
- **Repositories** (`src/wumpus_archiver/storage/repositories.py`): One class per entity. Takes `AsyncSession` in `__init__`. Core pattern is `upsert()` (check existence via `get_by_id()`, update or add). Uses `select()` statement API.
- **Database** (`src/wumpus_archiver/storage/database.py`): `connect()`/`disconnect()`/`create_tables()` lifecycle. `session()` is `@asynccontextmanager` with auto-commit/rollback.
- **Bot** (`src/wumpus_archiver/bot/scraper.py`): `ArchiverBot` wraps `commands.Bot` (composition, not inheritance). `scrape_guild()` is the main entry point.
- **API** (`src/wumpus_archiver/api/`): FastAPI app factory in `app.py`. 17 endpoints across 9 domain-split route modules in `routes/`. Pydantic response schemas in `schemas.py`. Background scrape manager in `scrape_manager.py`.
- **Portal** (`portal/`): SvelteKit 2 with adapter-static. Typed API client in `lib/api.ts`. 10 pages, 7 reusable components. Vite dev server proxies `/api` to FastAPI in development.
- **Config** (`src/wumpus_archiver/config.py`): pydantic-settings `BaseSettings` with `.env` support, `@lru_cache` singleton via `get_settings()`. `GUILD_ID` defaults target server for CLI commands.
- **CLI** (`src/wumpus_archiver/cli.py`): click-based, 6 subcommands: `scrape`, `serve`, `dev`, `download`, `init`, `update`.

## Build and Test

```bash
pip install -e ".[dev]"            # Install Python deps
cd portal && npm install && cd ..  # Install frontend deps
make dev                           # Start dev (backend + frontend)
make serve-build                   # Build + start production
make lint                          # ruff + mypy + svelte-check
make format                        # ruff --fix + black
make test                          # pytest (asyncio_mode="auto")
make test-cov                      # pytest + coverage
```

## Project Conventions

- **No base repository class** — each repository is standalone with its own `upsert()`/`get_by_id()`/query methods
- **Adding a model**: create in `models/`, re-export in `models/__init__.py`, add repository class in `storage/repositories.py`, re-export in `storage/__init__.py`
- **Adding an API endpoint**: add/edit route module in `api/routes/`, add schemas in `api/schemas.py`, register router in `api/routes/__init__.py` if new module
- **Adding a portal page**: create route in `portal/src/routes/`, add API function in `lib/api.ts`, add types in `lib/types.ts`
- **Async everywhere** — async engine, async sessions, `asyncio.run()` at CLI boundary
- **Configuration via `Field(validation_alias="ENV_VAR_NAME")`** in Settings class
- **No Firecrawl** — explicitly removed from scope; focus on core archival
- **SPA serving in production** — FastAPI serves built SvelteKit from `portal/build/` with index.html fallback

## Implementation Status

Phases 1–3.5 complete: models, repositories, database, bot scraper, config, CLI, FastAPI API (17 endpoints), SvelteKit portal (10 pages), unified dev command, Makefile.

**Not yet implemented**: FTS5 search, Alembic migrations, `update` command, export formats, analytics charts.

## Known Issues

- `bot/scraper.py` — rate limiting relies on discord.py's built-in handler; no custom header parsing
- `bulk_upsert` in `storage/repositories.py` is sequential — loops `upsert()`, not true bulk; optimize if performance matters
- Embeds stored as `str()` not JSON — known issue, should be `json.dumps()`
- Search uses SQL LIKE — should migrate to FTS5 for performance at scale

## IMPORTANT: Process management

- **Never leave background processes running.** If you start a server or dev process to test something, always kill it when done.
- Use `pkill -f "wumpus-archiver"` or kill the specific PID after verifying behavior.
- Before starting a new server instance, kill any existing ones first: `pkill -f "wumpus-archiver serve" 2>/dev/null; sleep 1`
- Do not start processes in the background (`&`) unless the user explicitly asks for a long-running server. Prefer foreground with a timeout for quick verification.

## IMPORTANT: warp intelligent tool usage guidelines

Fast Apply: IMPORTANT: Use `edit_file` over `str_replace` or full file writes. It works with partial code snippets—no need for full file content.
Warp Grep: warp-grep is a subagent that takes in a search string and tries to find relevant context. Best practice is to use it at the beginning of codebase explorations to fast track finding relevant files/lines. Do not use it to pin point keywords, but use it for broader semantic queries. "Find the XYZ flow", "How does XYZ work", "Where is XYZ handled?", "Where is <error message> coming from?"