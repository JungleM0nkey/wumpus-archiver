# Wumpus Archiver — Implementation Plan

## Status Summary

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Core Scraper | ✅ Complete | Models, repositories, bot scraper, CLI |
| 2. Storage & API | ✅ Complete | FastAPI app, 17 REST endpoints, schemas |
| 3. Portal Foundation | ✅ Complete | SvelteKit SPA, 10 pages, 7 components |
| 3.5. DevOps & Tooling | ✅ Complete | Unified dev/serve commands, Makefile |
| 4. Advanced Features | 🟡 Partial | Search working (SQL LIKE), gallery, downloads done; FTS5, exports, charts remaining |

---

## Phase 1: Core Scraper ✅

- SQLAlchemy 2.0 async models: Guild, Channel, User, Message, Attachment, Reaction
- `TimestampMixin` base class, `BigInteger` snowflake PKs
- Async database manager with session context manager
- Repository pattern: one class per entity with `upsert()` / `get_by_id()`
- `ArchiverBot` with discord.py — paginated history fetching
- Click CLI: `scrape`, `init` commands
- Pydantic settings with `.env` support

## Phase 2: Storage & API ✅

- FastAPI application factory (`create_app()`) with async lifespan
- 17 REST endpoints across 9 domain-split route modules
- Pydantic response schemas (~348 lines)
- CORS for dev server
- Background scrape job manager (start/cancel/status/history)
- Attachment download system (`ImageDownloader`) with progress tracking
- CLI: `serve`, `download` commands

## Phase 3: Portal Foundation ✅

- SvelteKit 2 with adapter-static (builds to `portal/build/`)
- Typed API client (`lib/api.ts`) with all endpoint functions
- TypeScript interfaces matching backend schemas
- Pages: Dashboard, Channels, Channel Messages, Channel Gallery, Guild Gallery, Timeline, Search, Users, User Profile, Control Panel
- Components: MessageCard, GalleryGrid, Lightbox, Nav, SearchBar, StatCard, TimelineFeed
- Vite proxy for development, SPA fallback serving in production

## Phase 3.5: DevOps & Tooling ✅

- `wumpus-archiver dev` — starts FastAPI + Vite dev server concurrently
- `wumpus-archiver serve --build-portal` — builds SPA then serves
- Async process manager with colored output, signal handling, graceful shutdown
- Makefile with targets: install, dev, serve, build, lint, format, test, clean
- Auto-generated `_dev_app.py` for uvicorn `--reload` support

---

## Phase 4: Advanced Features (Remaining Work)

### Search Enhancement
- [ ] Implement SQLite FTS5 virtual table for proper full-text search
- [ ] Add search filters (date range, user, channel)
- [ ] Search result highlighting
- [ ] Search suggestions / autocomplete

### Analytics & Visualization
- [ ] Message activity timeline chart
- [ ] User contribution statistics chart
- [ ] Channel activity heatmap
- [ ] Word frequency / word cloud

### Export Functionality
- [ ] JSON Lines exporter
- [ ] Static HTML generator (self-contained archive)
- [ ] CSV export for analysis
- [ ] Markdown export

### Incremental Updates
- [ ] Implement `update` command (currently a stub)
- [ ] Resume from `last_scraped_at` timestamp
- [ ] Handle edited / deleted messages
- [ ] Thread and forum channel support

### Database & Infrastructure
- [ ] Alembic migration framework
- [ ] SQLite → PostgreSQL migration tooling
- [ ] Database indexes on foreign keys (performance)
- [ ] True bulk upsert (replace sequential loop)

---

## Testing Strategy

### Unit Tests (partially implemented)
- [x] Model creation and relationships
- [x] Repository operations (CRUD, upsert)
- [x] Database connection lifecycle
- [x] Configuration loading and validation
- [x] CLI command registration
- [ ] API endpoint response shapes
- [ ] Scrape manager state machine

### Integration Tests (TODO)
- [ ] Full scrape → query roundtrip
- [ ] API ↔ database integration
- [ ] SPA serving and fallback
- [ ] Attachment download pipeline

### Load Tests (TODO)
- [ ] Large message batch processing
- [ ] Gallery pagination performance
- [ ] Search query performance at scale
