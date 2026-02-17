# Implementation Status — Channel-Level Scraping & Gallery Merge

_Last updated: 2025-02-12_

---

## Completed Work

### Feature 1: Channel-Level Scraping (Frontend + Backend)

Full implementation of the [CHANNEL_SCRAPE_FRONTEND.md](CHANNEL_SCRAPE_FRONTEND.md) spec — allows users to scrape individual channels instead of the entire guild.

#### Frontend Changes

| File | Changes |
|------|---------|
| `portal/src/lib/types.ts` | Added `ScrapeableChannel`, `ScrapeableChannelsResponse` interfaces. Updated `ScrapeJob` with `channel_ids: number[] \| null` and `scope: 'guild' \| 'channels'`. |
| `portal/src/lib/api.ts` | Added `getScrapeableChannels(guildId)`. Updated `startScrape(guildId, channelIds?)` to accept optional channel IDs. |
| `portal/src/routes/control/+page.svelte` | Mode toggle (Full Guild / Select Channels), channel selector with grouped/filterable checkbox list, category collapsing, select/deselect all, dynamic start button text, scope in live status card, scope column in history table. ~500 lines of new Svelte + CSS. |

#### Backend Changes

| File | Changes |
|------|---------|
| `src/wumpus_archiver/api/schemas.py` | Added `ScrapeableChannelSchema`, `ScrapeableChannelsResponse`, `ScrapeStartRequest.channel_ids`, `ScrapeJobSchema.channel_ids` + `scope`. |
| `src/wumpus_archiver/api/routes/scrape.py` | New `GET /scrape/guilds/{guild_id}/channels` endpoint. Updated `POST /scrape/start` to pass `channel_ids`. Added `_CHANNEL_TYPE_NAMES` mapping, `_job_to_schema` scope derivation. Hoisted imports to module level. |
| `src/wumpus_archiver/api/scrape_manager.py` | `ScrapeJob.channel_ids` field. `start_scrape()` accepts `channel_ids`. `_run_scrape()` uses cumulative progress tracking via `channel_done_callback`. Routes to `scrape_guild()` or `scrape_channels()` based on presence of `channel_ids`. |
| `src/wumpus_archiver/bot/scraper.py` | `scrape_guild()` and `scrape_channels()` accept `channel_done_callback`. New `scrape_channels()` method (~150 lines) handles selective channel scraping with thread discovery (active + archived) and deduplication. |

### Feature 2: Gallery → Channels Merge

Implemented the [GALLERY_CHANNELS_MERGE.md](GALLERY_CHANNELS_MERGE.md) roadmap — merged standalone gallery page into per-channel tabbed views.

| File | Action | Changes |
|------|--------|---------|
| `portal/src/lib/components/ChannelGallery.svelte` | **Created** | Reusable gallery component (grid + timeline views, lightbox, group-by pills). ~548 lines. |
| `portal/src/routes/channel/[id]/+page.svelte` | **Modified** | Added Messages/Gallery tab bar with URL-driven tab (`?tab=gallery`). Integrated `ChannelGallery` component. |
| `portal/src/routes/gallery/+page.svelte` | **Deleted** | Removed standalone gallery page. |
| `portal/src/lib/components/Nav.svelte` | **Modified** | Removed Gallery nav link. |

### Other Changes

| File | Changes |
|------|---------|
| `README.md` | Expanded Quick Start with prerequisites, venv setup, and clearer instructions. |
| `Makefile` | Added `venv` target, `install-py`, `install-js` targets. |
| `.github/copilot-instructions.md` | Added process management guidelines. |
| `src/wumpus_archiver/cli.py` | Fixed `download` command guild_id resolution scope issue. |

---

## Bug Fixes Applied (P0)

| # | Bug | Fix | File(s) |
|---|-----|-----|---------|
| 1 | `ScrapeStartRequest` had `channel_ids` defined twice | Removed duplicate field | `schemas.py` |
| 2 | `selectAllChannels()` selected all channels ignoring active filter | Scoped to visible (filtered) channels only; same for `deselectAllChannels()` | `+page.svelte` |
| 3 | `Number("abc")` → NaN sent to API as guild ID | Added `Number.isFinite(n) && n > 0` guard, returns `null` for invalid input | `+page.svelte` |

## Logic Gap Fixes (P1)

| # | Issue | Fix | File(s) |
|---|-------|-----|---------|
| 1 | `channels_done` stayed at 0 during scraping — progress callback only reported messages | Added `channel_done_callback` that tracks cumulative channels, messages, and attachments | `scrape_manager.py`, `scraper.py` |
| 2 | `scrape_channels()` didn't discover threads inside selected text channels | Added active + archived thread enumeration with dedup via `scraped_thread_ids` set | `scraper.py` |
| 3 | `list_scrapeable_channels` opened two separate DB sessions | Merged into single `async with db.session()` block | `routes/scrape.py` |
| 4 | `from sqlalchemy import select` etc. inside function body | Hoisted to module-level imports | `routes/scrape.py` |

---

## Verification

- **Frontend build**: `npm run build` → clean, no errors
- **Test suite**: `pytest tests/ -x -q` → **66 passed**, 2 warnings, 10.25s
- **Python imports**: All signatures verified programmatically

---

## Recent Additions (2026-02-16)

### Dual Database Support (SQLite + PostgreSQL)

| File | Changes |
|------|---------|
| `src/wumpus_archiver/storage/database.py` | Added `DatabaseRegistry` class for managing multiple named database sources with runtime switching. |
| `src/wumpus_archiver/config.py` | Added `POSTGRES_URL` setting (optional). |
| `src/wumpus_archiver/api/app.py` | Registers SQLite + PostgreSQL in `DatabaseRegistry`; defaults to PostgreSQL when configured. Added `TransferManager` to app state. |
| `src/wumpus_archiver/api/transfer_manager.py` | **Created** — Background data transfer (SQLite→PostgreSQL) with batch processing, progress tracking, cancellation, and automatic PostgreSQL sequence reset. |
| `src/wumpus_archiver/api/routes/datasource.py` | **Created** — `GET/PUT /datasource` for viewing and switching the active data source. |
| `src/wumpus_archiver/api/routes/transfer.py` | **Created** — `POST /transfer/start`, `GET /transfer/status`, `POST /transfer/cancel`. |
| `src/wumpus_archiver/api/schemas.py` | Added `DataSourceInfo`, `DataSourceResponse`, `DataSourceSetRequest`, `TransferStatusSchema`. |
| `portal/src/lib/types.ts` | Added `DataSourceInfo`, `DataSourceResponse`, `TransferStatus`. |
| `portal/src/lib/api.ts` | Added `getDataSource()`, `setDataSource()`, `startTransfer()`, `getTransferStatus()`, `cancelTransfer()`. |
| `portal/src/routes/control/+page.svelte` | Added Data Source section with source switcher and transfer controls with real-time progress. |

### Incremental Scraping

| File | Changes |
|------|---------|
| `src/wumpus_archiver/bot/scraper.py` | `_scrape_channel` checks `last_message_id` from DB; if set, passes `after=discord.Object(id=last_message_id)` with `oldest_first=True`. Fixed min/max tracking for message IDs regardless of iteration order. |
| `src/wumpus_archiver/storage/repositories.py` | Added `ChannelRepository.mark_scraped()` to update `last_scraped_at` when 0 new messages are found. |

### Per-Reaction Error Isolation

| File | Changes |
|------|---------|
| `src/wumpus_archiver/bot/scraper.py` | `_save_message` now flushes before reactions and handles each reaction individually with try/except + rollback/merge. Prevents one duplicate reaction from poisoning the entire message batch. |
| `src/wumpus_archiver/api/transfer_manager.py` | `_reset_sequences()` runs after every transfer to fix PostgreSQL auto-increment sequences for tables with integer PKs (e.g., `reactions`). |

### Scrape Progress Improvements

| File | Changes |
|------|---------|
| `portal/src/routes/control/+page.svelte` | Scraping phase now shows `channels_done / channels_total`. Replaced indeterminate pulse bar with real progress bar when total is known. |
| `portal/src/lib/types.ts` | Added `channels_total` to `ScrapeProgress` interface. |
| `src/wumpus_archiver/api/scrape_manager.py` | `ScrapeProgress.channels_total` is set when channel list is known. |

### Docker & CI/CD

| File | Changes |
|------|---------|
| `Dockerfile` | **Created** — Multi-stage Docker build (Python + Node for portal). |
| `docker-compose.yml` | **Created** — PostgreSQL + wumpus-archiver service. |
| `.github/workflows/ci.yml` | **Created** — Lint (ruff, mypy, svelte-check) + tests on PR/push. |
| `.github/workflows/release.yml` | **Created** — Docker image build + publish to GHCR on version tags. |

## Recent Additions (2026-02-17)

### Background Image Download Manager

| File | Changes |
|------|---------|
| `src/wumpus_archiver/api/download_manager.py` | **Created** — `DownloadManager` class wrapping `ImageDownloader` in a background `asyncio.Task` with progress tracking and cancellation. |
| `src/wumpus_archiver/api/routes/downloads.py` | Added `POST /downloads/start`, `GET /downloads/job`, `POST /downloads/cancel` endpoints. |
| `src/wumpus_archiver/api/schemas.py` | Added `DownloadJobStatus` schema. |
| `src/wumpus_archiver/api/app.py` | Wired `DownloadManager` into `app.state.download_manager`. |
| `portal/src/lib/types.ts` | Added `DownloadJobStatus` interface. |
| `portal/src/lib/api.ts` | Added `startDownload()`, `getDownloadJobStatus()`, `cancelDownload()`. |
| `portal/src/routes/control/+page.svelte` | Download button in Utilities drawer with live progress, cancel, and completion display. Shows attachments storage path. |

### Bug Fixes

| # | Bug | Fix | File(s) |
|---|-----|-----|---------|
| 1 | Scrape history only updated on page refresh | `pollStatus()` now detects busy→idle transitions and refreshes history. `handleStart()` also refreshes history immediately so pending jobs appear. | `+page.svelte` |
| 2 | Health-strip stats (messages, channels, last scraped) had empty space | Added `justify-content: space-between` and `flex: 1` to distribute stats evenly. | `+page.svelte` |
| 3 | `dlStats` not refreshed after scrape completes | `pollStatus()` now re-fetches download stats on scrape completion. | `+page.svelte` |
| 4 | "No attachments path configured" in Docker | `cli.py` serve/dev commands now `mkdir -p` the attachments directory instead of silently dropping the path when it doesn't exist. | `cli.py` |

---

## Outstanding Work

### P2 — UX Polish

| # | Issue | Description | File(s) |
|---|-------|-------------|---------|
| 1 | Reload clears selection | `loadChannels()` resets `selectedChannelIds` — the refresh button should preserve existing selection. | `+page.svelte` |

### P3 — Technical Debt

| # | Issue | Description | File(s) |
|---|-------|-------------|---------|
| 1 | Monolithic component | `control/+page.svelte` is ~1,800 lines. Extract `ChannelSelector.svelte` component with its own state, props for `selectedIds`, and events. | `+page.svelte` |
| 2 | Repeated Set cloning | `toggleChannel`, `selectAll`, `deselectAll`, `toggleCategory` all do `new Set(...)` manually. Create a reactive Set helper or use Svelte 5's `$state` with a Set wrapper. | `+page.svelte` |
| 3 | Duplicated channel icon mapping | `channelIcon()` in control page duplicates knowledge of channel types already in `types.ts` (`ChannelType` const). Move to a shared utility. | `+page.svelte`, `types.ts` |

### Not Yet Implemented (from project roadmap)

- FTS5 full-text search (currently uses SQL LIKE)
- Alembic database migrations
- Export formats (JSON, CSV)
- Analytics charts on dashboard
- Channel listing media preview thumbnails (Phase 3 of gallery merge)
