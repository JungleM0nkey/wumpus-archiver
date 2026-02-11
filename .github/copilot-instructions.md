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
- **Config** (`src/wumpus_archiver/config.py`): pydantic-settings `BaseSettings` with `.env` support, `@lru_cache` singleton via `get_settings()`.
- **CLI** (`src/wumpus_archiver/cli.py`): click-based, 4 subcommands: `scrape`, `serve`, `update`, `init`.

## Build and Test

```bash
pip install -e ".[dev]"            # Install with dev dependencies
black src/ tests/                  # Format
ruff check src/ tests/             # Lint
mypy src/                          # Type check
pytest                             # Test (asyncio_mode="auto", testpaths=["tests"])
pytest --cov=src/wumpus_archiver   # Test with coverage
```

## Project Conventions

- **No base repository class** — each repository is standalone with its own `upsert()`/`get_by_id()`/query methods
- **Adding a model**: create in `models/`, re-export in `models/__init__.py`, add repository class in `storage/repositories.py`, re-export in `storage/__init__.py`
- **Async everywhere** — async engine, async sessions, `asyncio.run()` at CLI boundary
- **Configuration via `Field(validation_alias="ENV_VAR_NAME")`** in Settings class
- **No Firecrawl** — explicitly removed from scope; focus on core archival
- **Embeds stored as `str()` not JSON** — known issue, should be `json.dumps()`
- **`bulk_upsert` is sequential** — loops `upsert()`, not true bulk; optimize if performance matters

## Implementation Status

Phase 1 (Core Scraper) is complete: models, repositories, database, bot scraper, config, CLI.
**Not yet implemented**: API endpoints (`api/`), tests (`tests/`), utils, Alembic migrations, SvelteKit portal, FTS5 search, `serve`/`update` CLI commands.

## Known Issues

- `models/reaction.py` — missing `Optional` import from typing
- `bot/scraper.py` — `bot.start()` method has empty body
- `TimestampMixin` in `models/base.py` is defined but not used by any model
