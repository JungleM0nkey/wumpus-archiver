# SQLite → PostgreSQL Data Transfer + Select Channels Bug Fix

## Bug Fix: Select Channels 500 Error

**Root cause**: `discord.http.HTTPClient()` requires a `loop` positional argument
in the discord.py version installed in Docker (v2.6.x). The constructor raises
`TypeError` which escapes the try/except in `fetch_live_channels()` because the
error occurs during `__init__`, before any awaited call.

**Fix**: Pass `asyncio.get_running_loop()` to `HTTPClient()` and ensure the
entire instantiation is inside the try/except so constructor failures fall back
to DB-only channel listing gracefully.

**Files**: `src/wumpus_archiver/api/scrape_manager.py` (lines 77-96)

---

## Feature: SQLite → PostgreSQL Data Transfer

### Goal

One-click data transfer from SQLite to PostgreSQL via the control panel,
running as a background job with real-time progress reporting.

### Architecture

Reuses the existing background job pattern from `ScrapeJobManager`.

**Transfer order** (respects foreign key dependencies):
1. Guilds (small, single batch)
2. Channels (small, single batch)
3. Users (small, single batch)
4. Messages (large, batched by 1000)
5. Attachments (large, batched by 1000)
6. Reactions (large, batched by 1000)

Each table is read from the source database session and upserted into the
target database session using raw SQLAlchemy (select all → insert with
on-conflict-do-update) for speed. The repository layer's individual `upsert()`
is too slow for bulk transfers.

### Backend

**New file**: `src/wumpus_archiver/api/transfer_manager.py`

```python
@dataclass
class TransferJob:
    status: str          # pending | running | completed | failed | cancelled
    current_table: str   # e.g. "messages"
    tables_done: int     # 0-6
    tables_total: int    # 6
    rows_transferred: int
    total_rows: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None
```

**New route module**: `src/wumpus_archiver/api/routes/transfer.py`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/transfer/start` | Start SQLite → PG transfer |
| GET | `/api/transfer/status` | Poll current job progress |
| POST | `/api/transfer/cancel` | Cancel running transfer |

**Transfer logic**:
- Reads from source DB using `select(Model)` with offset/limit batching
- Writes to target DB using SQLAlchemy `insert().on_conflict_do_update()`
- Counts total rows per table before starting for progress calculation
- Cancellation checked between batches via `asyncio.Event`

### Frontend

**Location**: New section in `/control` page, below existing scrape controls.

- Only visible when multiple data sources are configured
- Shows: source label, target label, transfer button
- During transfer: progress bar, current table, rows transferred / total
- On completion: success message with row counts
- On error: error message with details

### API Schemas

```python
class TransferStatusSchema(BaseModel):
    status: str
    current_table: str
    tables_done: int
    tables_total: int
    rows_transferred: int
    total_rows: int
    error: str | None
    started_at: str | None
    finished_at: str | None
```

### Files to Create/Modify

**Create:**
- `src/wumpus_archiver/api/transfer_manager.py` — TransferJob + transfer logic
- `src/wumpus_archiver/api/routes/transfer.py` — API endpoints

**Modify:**
- `src/wumpus_archiver/api/scrape_manager.py` — fix HTTPClient loop bug
- `src/wumpus_archiver/api/routes/__init__.py` — register transfer router
- `src/wumpus_archiver/api/schemas.py` — add TransferStatusSchema
- `portal/src/lib/api.ts` — add transfer API functions
- `portal/src/lib/types.ts` — add TransferStatus interface
- `portal/src/routes/control/+page.svelte` — add transfer UI section
