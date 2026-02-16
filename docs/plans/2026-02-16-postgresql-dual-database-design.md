# PostgreSQL Dual-Database Support

**Date**: 2026-02-16
**Status**: Approved

## Problem

The app currently only supports SQLite. We need PostgreSQL as a first-class data source, with the web UI able to switch between SQLite and PostgreSQL at runtime.

## Decisions

- **PostgreSQL on melmbox** — same server as the Docker container, no new containers needed
- **Scraper writes directly** to whichever DB is configured (no import/sync step)
- **Runtime toggle** — both databases connected at startup, UI switches between them live
- **Scrape targets active source** — whichever DB is toggled when you hit "Start Scrape"

## Architecture: Multi-Database App State

Both `Database` instances (SQLite + PostgreSQL) are initialized at startup. A `DatabaseRegistry` holds them and tracks which is active. All API routes resolve the active database per-request via the existing `get_db()` helper.

### Configuration (`config.py`)

Add optional `POSTGRES_URL` field to `Settings`. The existing `DATABASE_URL` remains the SQLite path. When both are configured, both sources are available.

### Database Registry (`storage/database.py`)

```python
class DatabaseRegistry:
    sources: dict[str, Database]  # "sqlite" -> Database, "postgres" -> Database
    active: str                   # current selection, default "sqlite"

    def get_active(self) -> Database
    def set_active(self, name: str) -> None
    async def connect_all(self) -> None   # connects + create_tables for each
    async def disconnect_all(self) -> None
```

The `Database` class stays unchanged.

### App Factory (`api/app.py`)

`create_app()` accepts both `database_url` (SQLite) and optional `postgres_url`. Creates a `DatabaseRegistry`, registers available sources, stores on `app.state.db_registry`. Lifespan calls `connect_all()` / `disconnect_all()`.

Backward compatible: if no `POSTGRES_URL`, works exactly as before with SQLite only.

### API Endpoints

**`GET /api/datasource`** — returns active source and available sources with metadata:
```json
{
  "active": "sqlite",
  "sources": {
    "sqlite": { "available": true, "label": "SQLite", "path": "/data/archive.db" },
    "postgres": { "available": true, "label": "PostgreSQL", "host": "localhost:5432/wumpus" }
  }
}
```

**`PUT /api/datasource`** — switches active source. Body: `{ "active": "postgres" }`. Returns 400 if source unavailable.

### Route Helper (`routes/_helpers.py`)

`get_db()` changes from `request.app.state.database` to `request.app.state.db_registry.get_active()`. All existing routes automatically use the active database.

### Scrape Manager

Gets a reference to `DatabaseRegistry` instead of single `Database`. Uses the active database at scrape-start time.

### Frontend

**Nav toggle**: Segmented control in the nav bar. Only renders when multiple sources are available. SQLite shows file path, PostgreSQL shows host/db name. Calls `PUT /api/datasource` on toggle, triggers data refetch.

**API client**: Add `getDataSource()` and `setDataSource(name)` functions.

**Types**: Add `DataSourceInfo` and `DataSourceResponse` interfaces.

No changes to existing page components — they all use the same API endpoints.

### CLI

`serve`, `dev`, and `scrape` commands get optional `--postgres-url` flag. If provided alongside the database file argument, both sources are available.

### Dependencies

Add `asyncpg` to default dependencies in `pyproject.toml`.

### Docker / dev.sh

Pass through `POSTGRES_URL` environment variable.

### Table Creation

`Base.metadata.create_all()` works identically for both dialects — models use standard SQLAlchemy types. `DatabaseRegistry.connect_all()` calls `create_tables()` on each source at startup.

## Files to Modify

1. `config.py` — add `POSTGRES_URL` field
2. `storage/database.py` — add `DatabaseRegistry` class
3. `api/app.py` — wire up registry in `create_app()`
4. `api/routes/_helpers.py` — update `get_db()` to use registry
5. `api/routes/datasource.py` — new route module (GET/PUT)
6. `api/routes/__init__.py` — register new router
7. `api/schemas.py` — add datasource response schemas
8. `api/scrape_manager.py` — use registry instead of single Database
9. `cli.py` — add `--postgres-url` to serve/dev/scrape commands
10. `portal/src/lib/api.ts` — add datasource API functions
11. `portal/src/lib/types.ts` — add datasource types
12. `portal/src/lib/components/Nav.svelte` — add toggle
13. `pyproject.toml` — add `asyncpg` dependency
14. `docker-compose.yml` — add `POSTGRES_URL` env var
15. `dev.sh` — pass through `POSTGRES_URL`
