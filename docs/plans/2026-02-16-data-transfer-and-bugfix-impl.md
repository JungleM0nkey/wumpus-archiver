# Data Transfer & Select Channels Bug Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the Select Channels 500 error and add SQLite → PostgreSQL one-click data transfer with progress tracking in the control panel.

**Architecture:** Two independent features: (1) a one-line bug fix in `fetch_live_channels` to pass the event loop to `discord.http.HTTPClient`, (2) a new `TransferManager` class with background job, three API endpoints, and a UI section in the control panel that mirrors the existing scrape job pattern.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, SvelteKit 5, Svelte 5 runes

---

### Task 1: Fix Select Channels 500 Error

The `discord.http.HTTPClient()` constructor requires a `loop` positional argument in discord.py v2.6.x. The current code at line 87 of `scrape_manager.py` calls `HTTPClient()` with no arguments, raising `TypeError` which escapes the `try/except` because the exception happens during `__init__()`, before any awaited call.

**Files:**
- Modify: `src/wumpus_archiver/api/scrape_manager.py:77-96`

**Step 1: Fix the HTTPClient instantiation**

Open `src/wumpus_archiver/api/scrape_manager.py`. Replace lines 77-96 (the entire `fetch_live_channels` method) with:

```python
    async def fetch_live_channels(self, token: str, guild_id: int) -> list[dict] | None:
        """Fetch live channel list from Discord HTTP API.

        Uses discord.http.HTTPClient directly for a single REST call
        instead of connecting a full gateway bot.

        Returns list of channel dicts or None on failure.
        """
        try:
            import discord.http

            http = discord.http.HTTPClient(loop=asyncio.get_running_loop())
            try:
                await http.static_login(token)
                channels = await http.get_all_guild_channels(guild_id)
                return channels  # type: ignore[return-value]
            finally:
                await http.close()
        except Exception as e:
            logger.warning("Failed to fetch live channels for guild %d: %s", guild_id, e)
            return None
```

Key changes:
- Moved `import discord.http` and `HTTPClient()` instantiation inside the outer `try/except` so constructor errors are caught
- Added `loop=asyncio.get_running_loop()` argument (note: `asyncio` is already imported at the top of this file)
- The outer `try/except` catches ALL errors (import, constructor, API) and gracefully returns `None`
- The inner `try/finally` ensures `http.close()` is called even if login/fetch fails

**Step 2: Verify the fix works**

Deploy to melmbox and test:
```bash
# Sync the file
rsync -avz src/wumpus_archiver/api/scrape_manager.py melmbox:/cloud/wumpus-archiver/src/wumpus_archiver/api/scrape_manager.py

# Rebuild and restart
ssh melmbox "cd /cloud/wumpus-archiver && docker compose build --no-cache && docker compose up -d"

# Test the endpoint
ssh melmbox "curl -s http://localhost:8200/api/scrape/guilds/165682173540696064/channels | python3 -m json.tool | head -20"
```

Expected: JSON response with channels (either live from Discord or fallback from DB), NOT a 500 error.

**Step 3: Commit**

```bash
git add src/wumpus_archiver/api/scrape_manager.py
git commit -m "fix: pass event loop to discord HTTPClient to fix Select Channels 500"
```

---

### Task 2: Add TransferManager backend

Create the `TransferManager` class that handles background SQLite → PostgreSQL data transfer with progress tracking.

**Files:**
- Create: `src/wumpus_archiver/api/transfer_manager.py`

**Step 1: Create the transfer manager**

Create `src/wumpus_archiver/api/transfer_manager.py` with the following content:

```python
"""Background data transfer manager for SQLite → PostgreSQL migration."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import DatabaseRegistry

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000

# Transfer order: respects foreign key dependencies
TABLES = [
    ("guilds", Guild),
    ("users", User),
    ("channels", Channel),
    ("messages", Message),
    ("attachments", Attachment),
    ("reactions", Reaction),
]


@dataclass
class TransferJob:
    """Tracks progress of a data transfer."""

    status: str = "pending"  # pending | running | completed | failed | cancelled
    current_table: str = ""
    tables_done: int = 0
    tables_total: int = len(TABLES)
    rows_transferred: int = 0
    total_rows: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TransferManager:
    """Manages background data transfers between database sources."""

    def __init__(self, registry: DatabaseRegistry) -> None:
        self._registry = registry
        self._job: TransferJob | None = None
        self._task: asyncio.Task[None] | None = None
        self._cancel_event = asyncio.Event()

    @property
    def current_job(self) -> TransferJob | None:
        return self._job

    @property
    def is_busy(self) -> bool:
        return self._job is not None and self._job.status in ("pending", "running")

    def start_transfer(self, source: str, target: str) -> TransferJob:
        """Start a background transfer from source to target database.

        Args:
            source: Registry name of the source database (e.g. "sqlite")
            target: Registry name of the target database (e.g. "postgres")

        Returns:
            The created TransferJob

        Raises:
            RuntimeError: If a transfer is already running
            KeyError: If source or target is not registered
        """
        if self.is_busy:
            raise RuntimeError("A transfer is already running")

        # Validate source and target exist
        src_db = self._registry.sources[source]
        tgt_db = self._registry.sources[target]

        job = TransferJob(started_at=datetime.now(UTC))
        self._job = job
        self._cancel_event.clear()

        self._task = asyncio.create_task(self._run_transfer(job, src_db, tgt_db))
        return job

    def cancel(self) -> bool:
        """Request cancellation of the current transfer."""
        if not self.is_busy or self._job is None:
            return False
        self._cancel_event.set()
        return True

    async def _run_transfer(self, job: TransferJob, src_db, tgt_db) -> None:
        """Execute the transfer in the background."""
        try:
            job.status = "running"
            logger.info("Transfer started")

            # Phase 1: Count total rows across all tables
            async with src_db.session() as session:
                for _table_name, model in TABLES:
                    result = await session.execute(select(func.count()).select_from(model))
                    job.total_rows += result.scalar_one()

            logger.info("Total rows to transfer: %d", job.total_rows)

            # Phase 2: Transfer each table
            for table_name, model in TABLES:
                if self._cancel_event.is_set():
                    job.status = "cancelled"
                    job.finished_at = datetime.now(UTC)
                    logger.info("Transfer cancelled during %s", table_name)
                    return

                job.current_table = table_name
                logger.info("Transferring table: %s", table_name)

                await self._transfer_table(job, src_db, tgt_db, model)
                job.tables_done += 1

            job.status = "completed"
            job.finished_at = datetime.now(UTC)
            logger.info(
                "Transfer completed: %d rows in %d tables",
                job.rows_transferred,
                job.tables_done,
            )

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            logger.info("Transfer cancelled")

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.finished_at = datetime.now(UTC)
            logger.error("Transfer failed: %s", e)

    async def _transfer_table(self, job, src_db, tgt_db, model) -> None:
        """Transfer all rows of a single table in batches."""
        offset = 0

        while True:
            if self._cancel_event.is_set():
                return

            # Read batch from source
            async with src_db.session() as src_session:
                result = await src_session.execute(
                    select(model).offset(offset).limit(BATCH_SIZE)
                )
                rows = list(result.scalars().all())

                if not rows:
                    break

                # Detach rows from source session so we can use them in target
                for row in rows:
                    src_session.expunge(row)

            # Write batch to target
            async with tgt_db.session() as tgt_session:
                for row in rows:
                    await tgt_session.merge(row)

            job.rows_transferred += len(rows)
            offset += len(rows)

            logger.debug(
                "  %s: transferred %d rows (batch at offset %d)",
                model.__tablename__,
                len(rows),
                offset - len(rows),
            )
```

**Key design decisions:**
- Uses `session.merge()` which acts as upsert — inserts new rows, updates existing ones
- `expunge()` detaches ORM objects from the source session before merging into target
- Batches of 1000 rows for memory efficiency on large tables
- `asyncio.Event` for cooperative cancellation between batches
- Total row count calculated upfront for accurate progress percentage
- Table order respects foreign key dependencies (guilds before channels before messages, etc.)
- Users transferred before channels/messages since messages have `author_id` FK

**Step 2: Verify the file is syntactically correct**

```bash
python -c "import ast; ast.parse(open('src/wumpus_archiver/api/transfer_manager.py').read()); print('OK')"
```

**Step 3: Commit**

```bash
git add src/wumpus_archiver/api/transfer_manager.py
git commit -m "feat: add TransferManager for SQLite → PostgreSQL data migration"
```

---

### Task 3: Add transfer API schemas and endpoints

Create the API layer: Pydantic schema, route module, and router registration.

**Files:**
- Modify: `src/wumpus_archiver/api/schemas.py` (append new schema)
- Create: `src/wumpus_archiver/api/routes/transfer.py`
- Modify: `src/wumpus_archiver/api/routes/__init__.py` (register router)
- Modify: `src/wumpus_archiver/api/app.py` (store TransferManager on app state)

**Step 1: Add TransferStatusSchema to schemas.py**

Append to the end of `src/wumpus_archiver/api/schemas.py` (after line 399, after the `DataSourceResponse` class):

```python


# --- Transfer schemas ---


class TransferStatusSchema(BaseModel):
    """Status of a data transfer job."""

    status: str
    current_table: str
    tables_done: int
    tables_total: int
    rows_transferred: int
    total_rows: int
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
```

**Step 2: Create the transfer route module**

Create `src/wumpus_archiver/api/routes/transfer.py`:

```python
"""Data transfer API route handlers."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from wumpus_archiver.api.schemas import TransferStatusSchema
from wumpus_archiver.api.transfer_manager import TransferManager

router = APIRouter()


def _get_transfer_manager(request: Request) -> TransferManager:
    return request.app.state.transfer_manager


def _job_to_schema(job) -> dict:
    """Convert a TransferJob to a dict matching TransferStatusSchema."""
    return TransferStatusSchema(
        status=job.status,
        current_table=job.current_table,
        tables_done=job.tables_done,
        tables_total=job.tables_total,
        rows_transferred=job.rows_transferred,
        total_rows=job.total_rows,
        error=job.error,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    ).model_dump()


@router.post("/transfer/start")
async def transfer_start(request: Request) -> JSONResponse:
    """Start a data transfer from SQLite to PostgreSQL."""
    manager = _get_transfer_manager(request)
    registry = request.app.state.db_registry

    if len(registry.available_sources) < 2:
        return JSONResponse(
            status_code=400,
            content={"error": "Need at least two data sources configured to transfer."},
        )

    if manager.is_busy:
        return JSONResponse(
            status_code=409,
            content={"error": "A transfer is already running"},
        )

    try:
        job = manager.start_transfer("sqlite", "postgres")
        return JSONResponse(status_code=202, content=_job_to_schema(job))
    except KeyError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.get("/transfer/status")
async def transfer_status(request: Request) -> JSONResponse:
    """Get current transfer job status."""
    manager = _get_transfer_manager(request)
    job = manager.current_job

    if job is None:
        return JSONResponse(
            content=TransferStatusSchema(
                status="idle",
                current_table="",
                tables_done=0,
                tables_total=0,
                rows_transferred=0,
                total_rows=0,
            ).model_dump()
        )

    return JSONResponse(content=_job_to_schema(job))


@router.post("/transfer/cancel")
async def transfer_cancel(request: Request) -> JSONResponse:
    """Cancel the current transfer."""
    manager = _get_transfer_manager(request)

    if manager.cancel():
        return JSONResponse(content={"message": "Cancellation requested"})

    return JSONResponse(
        status_code=404,
        content={"error": "No running transfer to cancel"},
    )
```

**Step 3: Register the transfer router**

Edit `src/wumpus_archiver/api/routes/__init__.py`. Add the import and registration:

After the existing import of `datasource_router` (line 6), add:
```python
from wumpus_archiver.api.routes.transfer import router as transfer_router
```

After the existing `router.include_router(datasource_router)` line (line 27), add:
```python
router.include_router(transfer_router)
```

**Step 4: Wire TransferManager into the app factory**

Edit `src/wumpus_archiver/api/app.py`.

Add import at line 12 (after the `ScrapeJobManager` import):
```python
from wumpus_archiver.api.transfer_manager import TransferManager
```

After the line `app.state.scrape_manager = ScrapeJobManager(registry)` (line 70), add:
```python
    app.state.transfer_manager = TransferManager(registry)
```

**Step 5: Verify syntax**

```bash
python -c "
import ast
for f in [
    'src/wumpus_archiver/api/schemas.py',
    'src/wumpus_archiver/api/routes/transfer.py',
    'src/wumpus_archiver/api/routes/__init__.py',
    'src/wumpus_archiver/api/app.py',
]:
    ast.parse(open(f).read())
    print(f'{f}: OK')
"
```

**Step 6: Commit**

```bash
git add src/wumpus_archiver/api/schemas.py src/wumpus_archiver/api/routes/transfer.py src/wumpus_archiver/api/routes/__init__.py src/wumpus_archiver/api/app.py
git commit -m "feat: add transfer API endpoints (start, status, cancel)"
```

---

### Task 4: Add frontend transfer types and API functions

Add TypeScript types and API client functions for the transfer feature.

**Files:**
- Modify: `portal/src/lib/types.ts` (append interface)
- Modify: `portal/src/lib/api.ts` (append functions)

**Step 1: Add TransferStatus interface**

Append to the end of `portal/src/lib/types.ts` (after the `DataSourceResponse` interface, around line 318):

```typescript

// --- Data transfer types ---

export interface TransferStatus {
	status: 'idle' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
	current_table: string;
	tables_done: number;
	tables_total: number;
	rows_transferred: number;
	total_rows: number;
	error: string | null;
	started_at: string | null;
	finished_at: string | null;
}
```

**Step 2: Add transfer API functions**

Append to the end of `portal/src/lib/api.ts` (after the `setDataSource` function, around line 183):

```typescript

// --- Data transfer ---

export async function getTransferStatus(): Promise<TransferStatus> {
	return fetchJSON<TransferStatus>('/transfer/status');
}

export async function startTransfer(): Promise<TransferStatus> {
	return fetchJSON<TransferStatus>('/transfer/start', {
		method: 'POST'
	});
}

export async function cancelTransfer(): Promise<{ message: string }> {
	return fetchJSON<{ message: string }>('/transfer/cancel', {
		method: 'POST'
	});
}
```

Also add `TransferStatus` to the import block at the top of `api.ts`. The existing import (line 3-19) should include `TransferStatus` alongside the other types:

```typescript
import type {
	Guild,
	GuildDetail,
	MessageListResponse,
	SearchResponse,
	Stats,
	GalleryResponse,
	TimelineGalleryResponse,
	ScrapeStatusResponse,
	ScrapeHistoryResponse,
	ScrapeJob,
	ScrapeableChannelsResponse,
	DownloadStatsResponse,
	UserListResponse,
	UserProfile,
	DataSourceResponse,
	TransferStatus
} from './types';
```

**Step 3: Commit**

```bash
git add portal/src/lib/types.ts portal/src/lib/api.ts
git commit -m "feat: add transfer types and API functions to frontend"
```

---

### Task 5: Add Data Transfer UI section to Control Panel

Add a "Data Transfer" section to the control panel page that shows transfer controls and progress.

**Files:**
- Modify: `portal/src/routes/control/+page.svelte`

**Step 1: Add imports and state**

In the `<script>` tag of `portal/src/routes/control/+page.svelte`:

Add to the imports from `$lib/api` (line 3-11): add `getTransferStatus`, `startTransfer`, `cancelTransfer`, `getDataSource`.

```typescript
import {
    getGuilds,
    getScrapeStatus,
    startScrape,
    cancelScrape,
    getScrapeHistory,
    getDownloadStats,
    getScrapeableChannels,
    getTransferStatus,
    startTransfer,
    cancelTransfer,
    getDataSource
} from '$lib/api';
```

Add to the type imports (line 12-19): add `TransferStatus`, `DataSourceResponse`.

```typescript
import type {
    Guild,
    ScrapeJob,
    ScrapeStatusResponse,
    ScrapeHistoryResponse,
    DownloadStatsResponse,
    ScrapeableChannel,
    TransferStatus,
    DataSourceResponse
} from '$lib/types';
```

After the existing state declarations (after `let channelFilter = $state('');` at line 40), add:

```typescript
	// Data transfer state
	let transferStatus: TransferStatus | null = $state(null);
	let datasourceInfo: DataSourceResponse | null = $state(null);
	let transferError = $state('');
	let transferPollTimer: ReturnType<typeof setInterval> | null = null;
```

Add derived values after the existing derived block (after `let selectedCount = ...` around line 72):

```typescript
	let showTransfer = $derived(
		datasourceInfo !== null && Object.keys(datasourceInfo.sources).length >= 2
	);
	let transferBusy = $derived(
		transferStatus?.status === 'pending' || transferStatus?.status === 'running'
	);
	let transferPercent = $derived(() => {
		if (!transferStatus || transferStatus.total_rows === 0) return 0;
		return Math.round((transferStatus.rows_transferred / transferStatus.total_rows) * 100);
	});
```

**Step 2: Add transfer functions**

After the existing `loadAll()` function (around line 192), add:

```typescript
	async function loadTransferInfo() {
		try {
			const [ds, ts] = await Promise.all([
				getDataSource().catch(() => null),
				getTransferStatus().catch(() => null)
			]);
			datasourceInfo = ds;
			transferStatus = ts;
		} catch {
			// Silently fail
		}
	}

	async function handleStartTransfer() {
		transferError = '';
		try {
			await startTransfer();
			transferStatus = await getTransferStatus();
			startTransferPolling();
		} catch (e) {
			transferError = e instanceof Error ? e.message : 'Failed to start transfer';
		}
	}

	async function handleCancelTransfer() {
		transferError = '';
		try {
			await cancelTransfer();
			transferStatus = await getTransferStatus();
		} catch (e) {
			transferError = e instanceof Error ? e.message : 'Failed to cancel transfer';
		}
	}

	function startTransferPolling() {
		if (transferPollTimer) return;
		transferPollTimer = setInterval(async () => {
			try {
				transferStatus = await getTransferStatus();
				if (transferStatus && !['pending', 'running'].includes(transferStatus.status)) {
					stopTransferPolling();
				}
			} catch {
				// Silently fail
			}
		}, 1000);
	}

	function stopTransferPolling() {
		if (transferPollTimer) {
			clearInterval(transferPollTimer);
			transferPollTimer = null;
		}
	}
```

Modify the existing `loadAll()` function to also call `loadTransferInfo()`. Add `loadTransferInfo()` to the `Promise.all` or call it after. Simplest approach — add a call after the existing `try` block inside `loadAll()`:

After `dlStats = dl;` (line 183), add:
```typescript
			await loadTransferInfo();
```

Modify the existing `onDestroy` to also clean up the transfer timer. Change line 168-170 from:
```typescript
	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
	});
```
to:
```typescript
	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
		stopTransferPolling();
	});
```

Also, if `transferBusy` is true on load, start polling. Add an `$effect` after the existing channel-loading effect (after line 93):

```typescript
	$effect(() => {
		if (transferBusy) startTransferPolling();
	});
```

**Step 3: Add the transfer section HTML**

In the template, after the Downloads section closing `{/if}` (after line 686) and before the History section (line 688), add:

```svelte
		<!-- Data Transfer -->
		{#if showTransfer}
			<section class="transfer-section fade-in" style="animation-delay: 0.09s">
				<h2 class="section-title">
					<span class="section-icon">⇄</span>
					Data Transfer
				</h2>

				<div class="transfer-card">
					<div class="transfer-overview">
						<div class="transfer-direction">
							<span class="transfer-source">
								SQLite
								{#if datasourceInfo}
									<span class="transfer-detail mono">{datasourceInfo.sources['sqlite']?.detail ?? ''}</span>
								{/if}
							</span>
							<span class="transfer-arrow">→</span>
							<span class="transfer-target">
								PostgreSQL
								{#if datasourceInfo}
									<span class="transfer-detail mono">{datasourceInfo.sources['postgres']?.detail ?? ''}</span>
								{/if}
							</span>
						</div>
					</div>

					{#if transferStatus && transferStatus.status !== 'idle'}
						<div class="transfer-progress">
							<div class="transfer-status-row">
								<span
									class="status-badge"
									style="color: {statusColor(transferStatus.status)}"
								>
									{statusIcon(transferStatus.status)} {transferStatus.status}
								</span>
								{#if transferStatus.current_table}
									<span class="mono" style="color: var(--text-secondary); font-size: 12px">
										{transferStatus.current_table}
									</span>
								{/if}
							</div>

							<div class="transfer-stats">
								<span class="mono">{transferStatus.rows_transferred.toLocaleString()} / {transferStatus.total_rows.toLocaleString()} rows</span>
								<span class="mono">{transferStatus.tables_done} / {transferStatus.tables_total} tables</span>
								<span class="mono">{transferPercent()}%</span>
							</div>

							<div class="dl-progress-bar">
								<div
									class="dl-progress-fill"
									style="width: {transferPercent()}%"
								></div>
							</div>

							{#if transferStatus.error}
								<div class="inline-error" style="margin-top: var(--sp-3)">
									{transferStatus.error}
								</div>
							{/if}
						</div>
					{/if}

					{#if transferError}
						<div class="inline-error">{transferError}</div>
					{/if}

					<div class="transfer-actions">
						{#if transferBusy}
							<button class="btn btn-danger" onclick={handleCancelTransfer}>
								⊘ Cancel Transfer
							</button>
						{:else}
							<button
								class="btn btn-primary"
								onclick={handleStartTransfer}
							>
								⇄ Transfer SQLite → PostgreSQL
							</button>
						{/if}
					</div>
				</div>
			</section>
		{/if}
```

**Step 4: Add CSS for the transfer section**

Append these styles inside the `<style>` tag (before the closing `</style>`):

```css
	/* Data Transfer Section */
	.transfer-section {
		margin-bottom: var(--sp-8);
	}

	.transfer-card {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		padding: var(--sp-5);
	}

	.transfer-overview {
		margin-bottom: var(--sp-4);
	}

	.transfer-direction {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		justify-content: center;
		padding: var(--sp-3);
		background: var(--bg-raised);
		border-radius: var(--radius-md);
	}

	.transfer-source,
	.transfer-target {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		font-weight: 600;
		font-size: 14px;
	}

	.transfer-detail {
		font-size: 11px;
		color: var(--text-muted);
		font-weight: 400;
		max-width: 200px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.transfer-arrow {
		font-size: 20px;
		color: var(--accent);
		font-weight: 700;
	}

	.transfer-progress {
		margin-bottom: var(--sp-4);
	}

	.transfer-status-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: var(--sp-2);
	}

	.transfer-stats {
		display: flex;
		justify-content: space-between;
		font-size: 12px;
		color: var(--text-secondary);
		margin-bottom: var(--sp-2);
	}

	.transfer-actions {
		display: flex;
		justify-content: center;
		gap: var(--sp-3);
	}
```

**Step 5: Verify frontend compiles**

```bash
cd portal && npm run check
```

Look for errors specifically in `control/+page.svelte`. Pre-existing errors in other files are OK.

**Step 6: Commit**

```bash
git add portal/src/routes/control/+page.svelte
git commit -m "feat: add data transfer UI section to control panel"
```

---

### Task 6: Deploy and verify end-to-end

Deploy all changes to the melmbox Docker container and verify both features work.

**Step 1: Sync all changed files to melmbox**

```bash
rsync -avz --delete \
  src/wumpus_archiver/ \
  melmbox:/cloud/wumpus-archiver/src/wumpus_archiver/

rsync -avz --delete \
  --exclude 'node_modules' \
  --exclude '.svelte-kit' \
  --exclude 'build' \
  portal/ \
  melmbox:/cloud/wumpus-archiver/portal/
```

**Step 2: Rebuild and restart**

```bash
ssh melmbox "cd /cloud/wumpus-archiver && docker compose build --no-cache && docker compose up -d"
```

Wait for the build to complete (this takes ~2-3 minutes).

**Step 3: Verify the bug fix**

```bash
ssh melmbox "curl -s http://localhost:8200/api/scrape/guilds/165682173540696064/channels | python3 -m json.tool | head -5"
```

Expected: JSON with `guild_id`, `guild_name`, `channels` array — NOT a 500 error.

**Step 4: Verify transfer endpoints**

```bash
# Check status (should return idle)
ssh melmbox "curl -s http://localhost:8200/api/transfer/status | python3 -m json.tool"

# Start a transfer
ssh melmbox "curl -s -X POST http://localhost:8200/api/transfer/start | python3 -m json.tool"

# Check progress
ssh melmbox "curl -s http://localhost:8200/api/transfer/status | python3 -m json.tool"
```

Expected: Status endpoint returns idle initially, start returns 202 with job data, subsequent status polls show progress.

**Step 5: Verify the UI**

Open the web portal in a browser, navigate to the Control page. Verify:
- The "Data Transfer" section appears (since PostgreSQL is configured)
- It shows "SQLite → PostgreSQL" with file paths
- The "Transfer" button works and shows progress
- After completion, the progress bar shows 100%

**Step 6: Commit all remaining changes and tag**

```bash
git add -A
git commit -m "feat: complete SQLite → PostgreSQL data transfer with UI"
```
