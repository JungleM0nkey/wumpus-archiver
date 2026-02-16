# PostgreSQL Dual-Database Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add PostgreSQL as a first-class data source alongside SQLite, with a runtime-switchable toggle in the web UI.

**Architecture:** A `DatabaseRegistry` holds both `Database` instances (SQLite + PostgreSQL), initialized at startup. All API routes resolve the active database via `get_db()`. A new `/api/datasource` endpoint lets the frontend switch between them. The Nav component renders a toggle when multiple sources are configured.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (asyncpg driver), FastAPI, SvelteKit 2/Svelte 5, TypeScript

**Design Doc:** `docs/plans/2026-02-16-postgresql-dual-database-design.md`

---

### Task 1: Add asyncpg dependency

**Files:**
- Modify: `pyproject.toml:25-37` (dependencies section)

**Step 1: Move asyncpg from optional to required**

In `pyproject.toml`, add `asyncpg` to the main `dependencies` list and remove the `[postgres]` optional group:

```toml
dependencies = [
    "discord.py>=2.3.0",
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.19.0",
    "asyncpg>=0.29.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-multipart>=0.0.6",
    "aiofiles>=23.2.0",
    "aiohttp>=3.9.0",
    "fastmcp>=2.0.0",
]
```

Remove the `[project.optional-dependencies] postgres` section (lines 40-42).

**Step 2: Install updated dependencies**

Run: `uv sync`
Expected: asyncpg installed, lock file updated

**Step 3: Verify import**

Run: `uv run python -c "import asyncpg; print(asyncpg.__version__)"`
Expected: version number printed

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add asyncpg as required dependency for PostgreSQL support"
```

---

### Task 2: Add POSTGRES_URL to config

**Files:**
- Modify: `src/wumpus_archiver/config.py:24-27`

**Step 1: Add the field to Settings**

After the existing `database_url` field, add:

```python
    postgres_url: str | None = Field(
        default=None,
        validation_alias="POSTGRES_URL",
    )
```

**Step 2: Verify it loads from env**

Run: `uv run python -c "from wumpus_archiver.config import Settings; s = Settings(DISCORD_BOT_TOKEN='test'); print(s.postgres_url)"`
Expected: `None`

Run: `POSTGRES_URL='postgresql+asyncpg://localhost/test' uv run python -c "from wumpus_archiver.config import Settings; s = Settings(DISCORD_BOT_TOKEN='test'); print(s.postgres_url)"`
Expected: `postgresql+asyncpg://localhost/test`

**Step 3: Commit**

```bash
git add src/wumpus_archiver/config.py
git commit -m "feat: add POSTGRES_URL config field"
```

---

### Task 3: Create DatabaseRegistry

**Files:**
- Modify: `src/wumpus_archiver/storage/database.py` (append after Database class)

**Step 1: Write DatabaseRegistry class**

Append to `src/wumpus_archiver/storage/database.py`:

```python
class DatabaseRegistry:
    """Manages multiple database sources with runtime switching."""

    def __init__(self) -> None:
        self.sources: dict[str, Database] = {}
        self.source_urls: dict[str, str] = {}
        self.active: str = "sqlite"

    def register(self, name: str, database: Database, url: str) -> None:
        """Register a named database source."""
        self.sources[name] = database
        self.source_urls[name] = url
        if len(self.sources) == 1:
            self.active = name

    def get_active(self) -> Database:
        """Get the currently active database."""
        if self.active not in self.sources:
            raise RuntimeError(f"Active data source '{self.active}' not registered")
        return self.sources[self.active]

    def set_active(self, name: str) -> None:
        """Switch the active data source."""
        if name not in self.sources:
            raise KeyError(f"Unknown data source: '{name}'. Available: {list(self.sources.keys())}")
        self.active = name

    @property
    def available_sources(self) -> list[str]:
        """List registered source names."""
        return list(self.sources.keys())

    async def connect_all(self) -> None:
        """Connect and create tables for all registered sources."""
        for name, db in self.sources.items():
            await db.connect()
            await db.create_tables()

    async def disconnect_all(self) -> None:
        """Disconnect all registered sources."""
        for db in self.sources.values():
            await db.disconnect()
```

**Step 2: Verify import**

Run: `uv run python -c "from wumpus_archiver.storage.database import DatabaseRegistry; r = DatabaseRegistry(); print(r.available_sources)"`
Expected: `[]`

**Step 3: Commit**

```bash
git add src/wumpus_archiver/storage/database.py
git commit -m "feat: add DatabaseRegistry for multi-source database management"
```

---

### Task 4: Add datasource API schemas

**Files:**
- Modify: `src/wumpus_archiver/api/schemas.py` (append at end)

**Step 1: Add schema classes**

Append to `src/wumpus_archiver/api/schemas.py`:

```python
# --- Data source schemas ---


class DataSourceInfo(BaseModel):
    """Info about a single data source."""

    available: bool = True
    label: str
    detail: str = ""  # file path for SQLite, host/db for PostgreSQL


class DataSourceSetRequest(BaseModel):
    """Request to switch the active data source."""

    active: str


class DataSourceResponse(BaseModel):
    """Current data source state."""

    active: str
    sources: dict[str, DataSourceInfo]
```

**Step 2: Verify import**

Run: `uv run python -c "from wumpus_archiver.api.schemas import DataSourceResponse; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/wumpus_archiver/api/schemas.py
git commit -m "feat: add datasource API schemas"
```

---

### Task 5: Create datasource route module

**Files:**
- Create: `src/wumpus_archiver/api/routes/datasource.py`
- Modify: `src/wumpus_archiver/api/routes/__init__.py:1-27`

**Step 1: Create the route file**

Create `src/wumpus_archiver/api/routes/datasource.py`:

```python
"""Data source switching API route handlers."""

from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from wumpus_archiver.api.schemas import (
    DataSourceInfo,
    DataSourceResponse,
    DataSourceSetRequest,
)
from wumpus_archiver.storage.database import DatabaseRegistry

router = APIRouter()


def _build_response(registry: DatabaseRegistry) -> DataSourceResponse:
    """Build a DataSourceResponse from the registry state."""
    sources: dict[str, DataSourceInfo] = {}
    for name in registry.available_sources:
        url = registry.source_urls.get(name, "")
        if name == "sqlite":
            # Extract file path from sqlite URL
            # e.g. "sqlite+aiosqlite:///./archive.db" -> "./archive.db"
            detail = url.split("///", 1)[-1] if "///" in url else url
            sources[name] = DataSourceInfo(label="SQLite", detail=detail)
        elif name == "postgres":
            # Extract host/db from postgres URL, strip credentials
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = f":{parsed.port}" if parsed.port and parsed.port != 5432 else ""
            db_name = parsed.path.lstrip("/") if parsed.path else ""
            detail = f"{host}{port}/{db_name}" if db_name else f"{host}{port}"
            sources[name] = DataSourceInfo(label="PostgreSQL", detail=detail)
        else:
            sources[name] = DataSourceInfo(label=name, detail=url)
    return DataSourceResponse(active=registry.active, sources=sources)


@router.get("/datasource", response_model=DataSourceResponse)
async def get_datasource(request: Request) -> DataSourceResponse:
    """Get current data source state and available sources."""
    registry: DatabaseRegistry = request.app.state.db_registry
    return _build_response(registry)


@router.put("/datasource", response_model=DataSourceResponse)
async def set_datasource(request: Request, body: DataSourceSetRequest) -> JSONResponse:
    """Switch the active data source."""
    registry: DatabaseRegistry = request.app.state.db_registry
    if body.active not in registry.available_sources:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Unknown data source: '{body.active}'. "
                f"Available: {registry.available_sources}"
            },
        )
    registry.set_active(body.active)
    return JSONResponse(content=_build_response(registry).model_dump())
```

**Step 2: Register the router in `__init__.py`**

In `src/wumpus_archiver/api/routes/__init__.py`, add the import and include:

```python
from wumpus_archiver.api.routes.datasource import router as datasource_router
```

And add:

```python
router.include_router(datasource_router)
```

**Step 3: Verify import**

Run: `uv run python -c "from wumpus_archiver.api.routes.datasource import router; print(len(router.routes), 'routes')"`
Expected: `2 routes`

**Step 4: Commit**

```bash
git add src/wumpus_archiver/api/routes/datasource.py src/wumpus_archiver/api/routes/__init__.py
git commit -m "feat: add datasource GET/PUT API endpoints"
```

---

### Task 6: Wire up DatabaseRegistry in app factory

**Files:**
- Modify: `src/wumpus_archiver/api/app.py`

**Step 1: Update create_app signature and body**

Change `create_app()` to accept a `DatabaseRegistry` instead of a single `Database`. Update the lifespan and app state accordingly.

The new signature:

```python
def create_app(
    database: Database | None = None,
    db_registry: DatabaseRegistry | None = None,
    attachments_path: Path | None = None,
    discord_token: str | None = None,
) -> FastAPI:
```

Add this import at the top:

```python
from wumpus_archiver.storage.database import Database, DatabaseRegistry
```

At the start of the function body, build the registry from either param:

```python
    # Build registry: accept either a single Database or a pre-built registry
    if db_registry is None:
        if database is None:
            raise ValueError("Either database or db_registry must be provided")
        db_registry = DatabaseRegistry()
        db_registry.register("sqlite", database, database.database_url)
    registry = db_registry
```

Update the lifespan:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle."""
        await registry.connect_all()
        yield
        await registry.disconnect_all()
```

Replace `app.state.database = database` with:

```python
    app.state.db_registry = registry
    # Backward compat: expose active database as app.state.database
    app.state.database = registry.get_active()
```

Update the ScrapeJobManager initialization to use the registry:

```python
    app.state.scrape_manager = ScrapeJobManager(registry)
```

**Step 2: Verify import**

Run: `uv run python -c "from wumpus_archiver.api.app import create_app; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/wumpus_archiver/api/app.py
git commit -m "feat: wire DatabaseRegistry into app factory and lifespan"
```

---

### Task 7: Update get_db() helper to use registry

**Files:**
- Modify: `src/wumpus_archiver/api/routes/_helpers.py:16-18`

**Step 1: Update get_db()**

Change the `get_db()` function:

```python
def get_db(request: Request) -> Database:
    """Get the active database from the registry."""
    return request.app.state.db_registry.get_active()  # type: ignore[no-any-return]
```

**Step 2: Commit**

```bash
git add src/wumpus_archiver/api/routes/_helpers.py
git commit -m "feat: get_db() now resolves from DatabaseRegistry"
```

---

### Task 8: Update ScrapeJobManager to use registry

**Files:**
- Modify: `src/wumpus_archiver/api/scrape_manager.py:53-70`

**Step 1: Update __init__ to accept DatabaseRegistry**

Change the import and constructor:

```python
from wumpus_archiver.storage.database import Database, DatabaseRegistry
```

Update `__init__`:

```python
    def __init__(self, registry: DatabaseRegistry) -> None:
        """Initialize the scrape job manager.

        Args:
            registry: DatabaseRegistry for resolving the active database
        """
        self._registry = registry
        self._current_job: ScrapeJob | None = None
        self._task: asyncio.Task[None] | None = None
        self._bot: ArchiverBot | None = None
        self._cancel_requested = False
        self._history: list[ScrapeJob] = []
```

**Step 2: Update _run_scrape to resolve database at scrape time**

In `_run_scrape()`, change the bot creation (around line 167) from:

```python
            bot = ArchiverBot(token, self.database)
```

to:

```python
            bot = ArchiverBot(token, self._registry.get_active())
```

**Step 3: Verify import**

Run: `uv run python -c "from wumpus_archiver.api.scrape_manager import ScrapeJobManager; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/wumpus_archiver/api/scrape_manager.py
git commit -m "feat: ScrapeJobManager uses DatabaseRegistry for active source"
```

---

### Task 9: Update CLI commands with --postgres-url

**Files:**
- Modify: `src/wumpus_archiver/cli.py`

**Step 1: Update `serve` command**

Add `--postgres-url` option to the `serve` command (after the `--build-portal` option):

```python
@click.option(
    "--postgres-url",
    default=None,
    help="PostgreSQL connection URL (e.g. postgresql+asyncpg://user:pass@host/db)",
)
```

Add `postgres_url: str | None` to the function signature.

In the function body, build a registry instead of a single Database:

```python
    from wumpus_archiver.storage.database import Database as DB, DatabaseRegistry

    # ... existing build_portal code ...

    registry = DatabaseRegistry()

    db_path = database.resolve()
    db_url = f"sqlite+aiosqlite:///{db_path}"
    registry.register("sqlite", DB(db_url), db_url)

    # Add PostgreSQL if configured (CLI flag or env)
    pg_url = postgres_url
    if not pg_url:
        try:
            from wumpus_archiver.config import Settings
            pg_url = Settings().postgres_url  # type: ignore[call-arg]
        except Exception:
            pass
    if pg_url:
        registry.register("postgres", DB(pg_url), pg_url)

    att_path = attachments_dir.resolve() if attachments_dir.exists() else None
    app = create_app(db_registry=registry, attachments_path=att_path)
```

**Step 2: Update `dev` command**

Same pattern — add `--postgres-url` option and pass it through. Update `_write_dev_app_module()` to accept and emit `postgres_url`.

Add to `_write_dev_app_module` signature: `postgres_url: str | None`

Update the generated module content to include registry setup:

```python
def _write_dev_app_module(db_path: Path, attachments_path: Path | None, postgres_url: str | None = None) -> None:
    dev_module = Path(__file__).parent / "api" / "_dev_app.py"
    att_line = f'    attachments_path=Path("{attachments_path}"),' if attachments_path else ""
    pg_lines = ""
    if postgres_url:
        pg_lines = f'''
from wumpus_archiver.storage.database import DatabaseRegistry
_registry = DatabaseRegistry()
_registry.register("sqlite", _db, "sqlite+aiosqlite:///{db_path}")
_registry.register("postgres", Database("{postgres_url}"), "{postgres_url}")
'''
    registry_arg = "    db_registry=_registry," if postgres_url else ""
    db_arg = "" if postgres_url else "    _db,"
    content = f'\'\'\'"""Auto-generated dev app instance for uvicorn --reload. DO NOT EDIT."""

from pathlib import Path

from wumpus_archiver.api.app import create_app
from wumpus_archiver.storage.database import Database

_db = Database("sqlite+aiosqlite:///{db_path}")
{pg_lines}
app = create_app(
{db_arg}
{registry_arg}
{att_line}
)
\'\'\''
    dev_module.write_text(content)
```

**Step 3: Update `scrape` command**

Add `--postgres-url` option. When provided, use PostgreSQL URL instead of SQLite file path:

```python
@click.option(
    "--postgres-url",
    default=None,
    help="Scrape directly into PostgreSQL instead of SQLite",
)
```

In the function body, when `postgres_url` is set, use it as the database URL instead of the SQLite file-based URL.

**Step 4: Commit**

```bash
git add src/wumpus_archiver/cli.py
git commit -m "feat: add --postgres-url to serve, dev, and scrape CLI commands"
```

---

### Task 10: Update dev.sh and docker-compose.yml

**Files:**
- Modify: `dev.sh`
- Modify: `docker-compose.yml`

**Step 1: Update dev.sh**

Add `POSTGRES_URL` passthrough. After the `exec` line, add the flag if the env var is set:

```bash
# Build command
CMD=(wumpus-archiver dev "$DB" --port "$PORT" --frontend-port "$VITE_PORT" -a "$ATT_DIR")

# Add PostgreSQL if configured
if [[ -n "${POSTGRES_URL:-}" ]]; then
    CMD+=(--postgres-url "$POSTGRES_URL")
fi

exec "${CMD[@]}"
```

(Replace the existing `exec wumpus-archiver dev ...` line.)

**Step 2: Update docker-compose.yml**

Add `POSTGRES_URL` to the environment section:

```yaml
    environment:
      - API_HOST=0.0.0.0
      - DATABASE_URL=sqlite+aiosqlite:////data/archive.db
      - ATTACHMENTS_PATH=/data/attachments
      - POSTGRES_URL=${POSTGRES_URL:-}
```

**Step 3: Commit**

```bash
git add dev.sh docker-compose.yml
git commit -m "feat: pass POSTGRES_URL through dev.sh and docker-compose"
```

---

### Task 11: Add frontend types and API functions

**Files:**
- Modify: `portal/src/lib/types.ts` (append at end)
- Modify: `portal/src/lib/api.ts` (append at end)

**Step 1: Add TypeScript types**

Append to `portal/src/lib/types.ts`:

```typescript
// --- Data source types ---

export interface DataSourceInfo {
	available: boolean;
	label: string;
	detail: string;
}

export interface DataSourceResponse {
	active: string;
	sources: Record<string, DataSourceInfo>;
}
```

**Step 2: Add API functions**

Append to `portal/src/lib/api.ts`:

```typescript
// --- Data source ---

export async function getDataSource(): Promise<DataSourceResponse> {
	return fetchJSON<DataSourceResponse>('/datasource');
}

export async function setDataSource(name: string): Promise<DataSourceResponse> {
	return fetchJSON<DataSourceResponse>('/datasource', {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ active: name })
	});
}
```

Add `DataSourceResponse` to the import list in `api.ts`.

**Step 3: Verify TypeScript compiles**

Run: `cd portal && npm run check`
Expected: no errors

**Step 4: Commit**

```bash
git add portal/src/lib/types.ts portal/src/lib/api.ts
git commit -m "feat: add datasource types and API functions to frontend"
```

---

### Task 12: Add data source toggle to Nav component

**Files:**
- Modify: `portal/src/lib/components/Nav.svelte`

**Step 1: Add data source toggle**

Update the script section to import and fetch data source state:

```typescript
import { onMount } from 'svelte';
import { page } from '$app/state';
import { getDataSource, setDataSource } from '$lib/api';
import type { DataSourceResponse } from '$lib/types';

// ... existing links array ...

let dataSource: DataSourceResponse | null = $state(null);
let switching = $state(false);

let showToggle = $derived(
    dataSource !== null && Object.keys(dataSource.sources).length > 1
);

onMount(async () => {
    try {
        dataSource = await getDataSource();
    } catch {
        // No datasource endpoint = single source mode
    }
});

async function handleSwitch(name: string) {
    if (!dataSource || name === dataSource.active || switching) return;
    switching = true;
    try {
        dataSource = await setDataSource(name);
        // Reload the page to refetch all data from new source
        window.location.reload();
    } catch {
        // Revert on failure
    } finally {
        switching = false;
    }
}
```

In the `nav-right` div, before the version span, add:

```html
{#if showToggle && dataSource}
    <div class="ds-toggle">
        {#each Object.entries(dataSource.sources) as [name, info]}
            <button
                class="ds-btn"
                class:active={name === dataSource.active}
                class:switching
                onclick={() => handleSwitch(name)}
                disabled={switching}
                title={info.detail}
            >
                {info.label}
            </button>
        {/each}
        <span class="ds-detail mono">{dataSource.sources[dataSource.active]?.detail ?? ''}</span>
    </div>
{/if}
```

Add styles:

```css
/* Data source toggle */
.ds-toggle {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
}

.ds-btn {
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
    border-radius: var(--radius-sm);
    background: var(--bg-raised);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s var(--ease-out);
}

.ds-btn:hover:not(:disabled) {
    color: var(--text-primary);
    border-color: var(--border-strong);
}

.ds-btn.active {
    background: var(--accent);
    color: var(--bg-base);
    border-color: var(--accent);
}

.ds-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.ds-detail {
    font-size: 10px;
    color: var(--text-muted);
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
```

**Step 2: Verify frontend builds**

Run: `cd portal && npm run check && npm run build`
Expected: no errors

**Step 3: Commit**

```bash
git add portal/src/lib/components/Nav.svelte
git commit -m "feat: add data source toggle to Nav bar"
```

---

### Task 13: Integration test — verify end-to-end

**Step 1: Start dev server with SQLite only**

Run: `./dev.sh`
Open browser, verify Nav does NOT show the toggle (single source).

**Step 2: Start dev server with both sources**

Run: `POSTGRES_URL='postgresql+asyncpg://user:pass@localhost/wumpus_test' ./dev.sh`
Open browser, verify Nav shows SQLite/PostgreSQL toggle.
Verify switching triggers page reload and data comes from the new source.

**Step 3: Verify control panel scraping**

Switch to PostgreSQL, start a scrape from the control panel.
Verify data lands in PostgreSQL.
Switch back to SQLite, verify old data still there.

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration test fixes for dual-database support"
```

---

### Task 14: Deploy to melmbox

**Step 1: Copy changed files to melmbox**

Use `scp` or `rsync` to push the updated files to `/cloud/wumpus-archiver/` on melmbox.

**Step 2: Set POSTGRES_URL in .env on melmbox**

Add to `/cloud/wumpus-archiver/.env`:
```
POSTGRES_URL=postgresql+asyncpg://user:pass@localhost:5432/wumpus_archive
```

(Use the actual PostgreSQL credentials on melmbox.)

**Step 3: Rebuild and restart**

```bash
ssh melmbox "cd /cloud/wumpus-archiver && docker compose build && docker compose up -d"
```

**Step 4: Verify in browser**

Open the portal, confirm the data source toggle appears and works.
