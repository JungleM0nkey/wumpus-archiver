# Wumpus Archiver — Implementation Review

**Last updated**: 2026-02-11
**Scope**: Full project — Phases 1–3.5

---

## Executive Summary

| Metric | Result |
|--------|--------|
| **Overall Assessment** | Functional — suitable for personal/small-team use |
| **Python source files** | 35 (~4,400 lines) |
| **Portal source files** | 25 (~6,400 lines) |
| **Test files** | 6 (~1,060 lines) |
| **API endpoints** | 17 across 9 route modules |
| **Portal pages** | 10 |

Phases 1–3 are complete and working. The system scrapes Discord servers, stores data in SQLite, and provides a full web portal for browsing archives. A unified `dev` command runs both servers with hot-reload. Production mode serves the SPA from FastAPI.

---

## What's Working

### Core Scraper (Phase 1)
- ✅ SQLAlchemy 2.0 async models with proper relationships
- ✅ Repository pattern with upsert semantics
- ✅ ArchiverBot with paginated history fetching
- ✅ Click CLI with scrape, init commands
- ✅ Pydantic settings with .env support
- ✅ Type annotations throughout (`Mapped[]`, `mapped_column()`)

### API Layer (Phase 2)
- ✅ FastAPI app factory with async lifespan
- ✅ 17 REST endpoints across 9 domain-split route modules
- ✅ Pydantic response schemas
- ✅ Background scrape job manager (start/cancel/status)
- ✅ Image attachment downloader with concurrency control
- ✅ Local attachment serving via StaticFiles mount

### Web Portal (Phase 3)
- ✅ SvelteKit 2 with adapter-static
- ✅ Typed API client and TypeScript interfaces
- ✅ Dashboard, channels, messages, gallery, timeline, search, users, control panel
- ✅ MessageCard component (embeds, attachments, reactions)
- ✅ GalleryGrid with Lightbox
- ✅ Responsive navigation

### DevOps (Phase 3.5)
- ✅ `wumpus-archiver dev` — concurrent backend + frontend
- ✅ `wumpus-archiver serve --build-portal` — one-command production
- ✅ Process manager with colored output and signal handling
- ✅ Makefile with all common targets

---

## Issues Fixed Since Initial Review

| # | Issue | Status |
|---|-------|--------|
| 3 | Missing `Optional` import in reaction model | ✅ Fixed (uses `X \| None` syntax) |
| 5 | Exit code 0 on errors | ✅ Fixed (returns 1 on errors) |
| 10 | Stub `serve` command | ✅ Implemented (full API + SPA serving) |
| 11 | Token exposure via `--token` flag | ✅ Fixed (token via env only) |
| 12 | Path traversal risk on `--output` | ✅ Fixed (path resolved + validated) |
| 13 | Version hardcoded | ✅ Fixed (uses `importlib.metadata`) |
| 15 | Missing config validation | ✅ Fixed (validators for port, batch_size, etc.) |

---

## Remaining Issues

### High Priority

1. **Rate limiting is basic** — relies on discord.py's built-in handler. No custom `X-RateLimit-*` header parsing. Works for small servers but may hit 429s on large guilds.

2. **`bulk_upsert` is sequential** — loops `upsert()` with individual SELECTs. O(n) queries per batch. Should use `INSERT ... ON CONFLICT` for true bulk operations.

3. **Search uses SQL LIKE** — no FTS5 virtual table. Performance degrades on large archives. Should implement proper full-text indexing.

4. **Missing database indexes** — foreign keys lack explicit indexes (guild_id, author_id, message_id). SQLite may auto-index some but not all.

### Medium Priority

5. **Embeds stored as `str()` not JSON** — should use `json.dumps()` for proper deserialization.

6. **No Alembic migrations** — schema changes require manual table recreation.

7. **`update` command is a stub** — incremental updates not yet implemented.

8. **No thread/forum channel support** — only `guild.text_channels` is iterated.

9. **Long-running transaction scope** — full guild scrape in one session. Should commit in batches for large servers.

### Low Priority

10. **No export functionality** — JSON/HTML/CSV exports not yet implemented.
11. **Naive datetime handling** — timezone info may be stripped in some paths.
12. **Race condition in counter updates** — `scrape_count += 1` is read-modify-write.

---

## Next Steps

### Immediate Wins
- [ ] Add FTS5 virtual table for search performance
- [ ] Add database indexes on foreign keys
- [ ] Fix embed serialization to use `json.dumps()`
- [ ] Commit in batches during scraping

### Medium Term
- [ ] Implement `update` command for incremental archiving
- [ ] Add thread/forum channel support
- [ ] Alembic migration framework
- [ ] Expand test coverage for API endpoints

### Future
- [ ] Analytics charts (activity timeline, heatmap)
- [ ] Export formats (JSON, HTML, CSV)
- [ ] Docker Compose setup
- [ ] PostgreSQL support testing
