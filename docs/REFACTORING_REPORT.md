# Work Report: API Routes Refactoring

**Date:** February 11, 2026  
**Scope:** `src/wumpus_archiver/api/routes.py` → `src/wumpus_archiver/api/routes/` package

---

## Summary

Refactored the monolithic 1,170-line `routes.py` into a domain-organized package of 11 focused modules. All 17 API endpoints preserved with identical behavior — zero breaking changes.

## What Changed

### Deleted
| File | Lines |
|------|-------|
| `api/routes.py` | 1,170 |

### Created
| File | Lines | Responsibility |
|------|-------|----------------|
| `api/routes/__init__.py` | 27 | Aggregates sub-routers into single `router` |
| `api/routes/_helpers.py` | 108 | `get_db()`, `rewrite_attachment_url()`, `rows_to_gallery_schemas()`, `IMAGE_TYPES` |
| `api/routes/guilds.py` | 82 | `GET /guilds`, `GET /guilds/{id}` |
| `api/routes/channels.py` | 28 | `GET /guilds/{id}/channels` |
| `api/routes/gallery.py` | 260 | `GET /channels/{id}/gallery`, `GET /guilds/{id}/gallery`, `GET /guilds/{id}/gallery/timeline` |
| `api/routes/messages.py` | 84 | `GET /channels/{id}/messages` |
| `api/routes/search.py` | 104 | `GET /search` |
| `api/routes/stats.py` | 98 | `GET /guilds/{id}/stats` |
| `api/routes/users.py` | 256 | `GET /users/{id}`, `GET /guilds/{id}/users`, `GET /users/{id}/profile` |
| `api/routes/scrape.py` | 115 | `GET /scrape/status`, `POST /scrape/start`, `POST /scrape/cancel`, `GET /scrape/history` |
| `api/routes/downloads.py` | 94 | `GET /downloads/stats` |
| **Total** | **1,256** | |

### Modified
| File | Change |
|------|--------|
| `api/app.py` | Import path updated (`api.routes` now resolves to the package) |

## Design Decisions

- **Shared helpers in `_helpers.py`** — `get_db()`, URL rewriting, gallery row conversion, and `IMAGE_TYPES` constant extracted once, imported by multiple modules. Eliminates duplication.
- **`_period_label()` extracted in `gallery.py`** — the timeline grouping logic had duplicated `__import__("datetime")` inline hacks; replaced with a clean helper function using a proper `datetime` import.
- **No import changes for `app.py`** — `from wumpus_archiver.api.routes import router` resolves identically whether `routes` is a module or a package with `__init__.py`.
- **Each module owns its own `APIRouter()`** — sub-routers are composed in `__init__.py` via `include_router()`, keeping each file independently testable.

## Verification

- All 17 routes registered (confirmed via Python import check)
- Server started and responded HTTP 200 on `GET /api/guilds`, `GET /api/search?q=hello`, `GET /api/downloads/stats`
- No changes to schemas, models, or any code outside `api/`

## Project Metrics (post-refactor)

| Metric | Value |
|--------|-------|
| Python source files | 33 |
| Total Python lines | 3,915 |
| `api/` package lines | 1,951 (routes: 1,256 + schemas: 348 + app: 122 + scrape_manager: 220 + init: 5) |
| Largest route module | `gallery.py` (260 lines) |
| Smallest route module | `channels.py` (28 lines) |
