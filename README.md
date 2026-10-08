# Wumpus Archiver

Self-hosted Discord server archival with a web exploration portal.

Scrape messages, channels, users, and attachments into a SQLite database, then browse everything through a SvelteKit UI served by FastAPI.

## Quick Start

```bash
pip install -e ".[dev]"
cd portal && npm install && cd ..
cp .env.example .env          # set DISCORD_BOT_TOKEN
```

Your Discord bot needs **Message Content** and **Server Members** privileged intents, plus Read Messages and Read Message History permissions.

```bash
# Scrape a server (uses GUILD_ID from .env, or pass --guild-id)
wumpus-archiver scrape
wumpus-archiver scrape --guild-id 123456789

# Download image attachments locally
wumpus-archiver download ./archive.db -v
```

## Running the App

### Development (hot-reload on both backend & frontend)

```bash
# Single command — starts FastAPI (uvicorn --reload) + Vite dev server
wumpus-archiver dev ./archive.db -a ./attachments

# Or using Make
make dev
```

Backend runs on `:8000`, frontend on `:5173` with Vite HMR and API proxy.
Press Ctrl+C to stop both.

### Production

```bash
# Build the portal then serve everything from one process
wumpus-archiver serve ./archive.db --build-portal -a ./attachments

# Or build and serve separately
cd portal && npm run build && cd ..
wumpus-archiver serve ./archive.db -a ./attachments

# Using Make
make serve-build   # build + serve
make serve         # serve only (portal must already be built)
```

## CLI Reference

| Command | Description |
|---|---|
| `wumpus-archiver init` | Initialize project (creates `.env`, directories) |
| `wumpus-archiver scrape` | Scrape a Discord server into SQLite (uses `GUILD_ID` from `.env`) |
| `wumpus-archiver download DB` | Download image attachments locally |
| `wumpus-archiver mirror` | Live-mirror Discord guild messages into apehost chat (runs until stopped) |
| `wumpus-archiver dev DB` | Start dev environment (backend + frontend, hot-reload) |
| `wumpus-archiver serve DB` | Start production server (API + built SPA) |
| `wumpus-archiver update DB` | Update archive with new messages *(not yet implemented)* |

All commands support `--help` for full options.

## Make Targets

Run `make help` for the full list. Highlights:

| Target | Description |
|---|---|
| `make install` | Install all dependencies (Python + Node) |
| `make dev` | Start dev environment (backend + frontend with hot-reload) |
| `make build` | Build the SvelteKit portal for production |
| `make serve` | Start production server (API + built portal) |
| `make serve-build` | Build portal then start production server |
| `make lint` | Run ruff + mypy + svelte-check |
| `make format` | Auto-format Python code (ruff + black) |
| `make test` | Run Python tests |
| `make test-cov` | Run tests with coverage report |
| `make clean` | Remove build artifacts and caches |

Override defaults with env vars: `DB=my.db PORT=9000 make dev`

## Project Structure

```
wumpus-archiver/
├── src/wumpus_archiver/       # Python backend
│   ├── cli.py                 # Click CLI (scrape, serve, dev, download, init)
│   ├── config.py              # Pydantic settings (.env support)
│   ├── models/                # SQLAlchemy 2.0 models (7 entities)
│   ├── storage/               # Database + repository layer
│   ├── bot/                   # Discord scraper (discord.py)
│   ├── api/                   # FastAPI app + route handlers
│   │   ├── app.py             # App factory with SPA serving
│   │   ├── schemas.py         # Pydantic response schemas
│   │   ├── scrape_manager.py  # Background scrape job manager
│   │   └── routes/            # Domain-split route modules (9 files)
│   └── utils/                 # Downloader, process manager
├── portal/                    # SvelteKit frontend (adapter-static)
│   └── src/
│       ├── lib/               # API client, components, types
│       └── routes/            # Pages (home, channels, gallery, search, etc.)
├── tests/                     # pytest test suite
├── docs/                      # Architecture & planning docs
├── Makefile                   # Convenience targets
└── pyproject.toml             # Project metadata & dependencies
```

## Tech Stack

- **Backend**: Python 3.12 · discord.py · FastAPI · SQLAlchemy 2.0 (async) · uvicorn
- **Database**: SQLite (aiosqlite) with optional PostgreSQL (asyncpg)
- **Frontend**: SvelteKit 3 · Svelte 5 · TypeScript 6 · Vite 8 (Node.js 22.17+)
- **Quality**: ruff · black · mypy · pytest · svelte-check

## API Endpoints

All endpoints are under `/api/`:

| Endpoint | Description |
|---|---|
| `GET /guilds` | List archived guilds |
| `GET /guilds/{id}` | Guild detail |
| `GET /guilds/{id}/channels` | Channel list for a guild |
| `GET /guilds/{id}/stats` | Guild statistics |
| `GET /guilds/{id}/users` | Users in a guild |
| `GET /guilds/{id}/gallery` | Image gallery for a guild |
| `GET /guilds/{id}/gallery/timeline` | The gallery timeline behind the Media screen: attachments grouped by month, filtered by `content_type` (image, gif, video, media), `channel_id` and `author_id` |
| `GET /channels/{id}/messages` | Paginated messages, newest first (`before`, `after`, `around` cursors); `pinned=true` lists only the pinned ones |
| `GET /channels/{id}/gallery` | Channel image gallery |
| `GET /search` | Message search: every term of `q` (a quoted phrase is one term), filtered by `guild_id`, `channel_id`, `author_id`, `has` (file, image, video, link) and `after`/`before` days in UTC (`after` inclusive, `before` exclusive), sorted `newest` or `oldest`, paged with `cursor`; results carry an escaped `highlight` snippet, and `facets=true` adds counts per channel, author and month |
| `GET /users/{id}/profile` | User profile with stats |
| `GET /downloads/stats` | Local attachment download stats |
| `GET /scrape/status` | Current scrape job status |
| `POST /scrape/start` | Start a scrape job |
| `POST /scrape/cancel` | Cancel running scrape |
| `GET /scrape/history` | Scrape job history |

## Portal Pages

A left sidebar, which collapses to an icon rail with Cmd+\ (Ctrl+\ elsewhere), holds a
guild switcher, a search field, the five destinations and an archive-status card that
leads to the Archive screen. The selected guild is part of the URL (`?guild=<id>`, the
first guild when absent), and every page shows that guild.

| Route | Destination | Description |
|---|---|---|
| `/` | Overview | Guild stats |
| `/browse` | Browse | Opens the guild's most active channel (`/channels` and `/timeline` redirect here) |
| `/browse/[channel]` | Browse | A channel's messages beside the channel pane; `?message=<id>` opens it on one message (`/channel/[id]` and `/timeline?channel=` redirect here); `?tab=media` and `?tab=pinned` show the channel's media and pinned messages |
| `/media` | Media | Images, GIFs and videos in justified rows under month headers, filtered by type, channel and sort in the URL (`/gallery` and `/channel/[id]/gallery` redirect here) |
| `/search` | Search | Messages holding every term, narrowed by filter chips typed into the query (`in:`, `from:`, `has:`, `after:`, `before:`); highlighted snippets open in context in Browse, a refine rail counts channels, people and months and adds their chips, and the query and sort live in the URL |
| `/people` | People | Authors as a table, sortable by messages, name or recent activity, searchable by name (`/users` redirects here) |
| `/people/[id]` | People | A profile: stat tiles, a 52-week activity heatmap, top channels, reactions received, recent messages (`/users/[id]` redirects here) |
| `/archive` | Archive screen (sidebar footer) | Scrape control: run a scrape, the live scrape job, attachments on disk, job history (`/control` redirects here) |

## Environment Variables

See `.env.example` for all options. Key variables:

| Variable | Default | Description |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *(required)* | Discord bot token |
| `GUILD_ID` | *(none)* | Target Discord server ID (used as default for `--guild-id`) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./wumpus_archive.db` | Database connection |
| `API_HOST` | `127.0.0.1` | API bind host |
| `API_PORT` | `8000` | API bind port |
| `API_AUTH_TOKEN` | *(none)* | Bearer token required by `POST /api/scrape/start` and `/api/scrape/cancel`; scrape control is disabled while unset |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000,http://localhost:8000,https://connect.apehost.net` | Comma-separated browser origins allowed to call the API cross-origin |
| `BATCH_SIZE` | `1000` | Messages per scrape batch |
| `RATE_LIMIT_DELAY` | `0.5` | Delay between API calls |
| `DOWNLOAD_ATTACHMENTS` | `true` | Auto-download attachments |
| `ATTACHMENTS_PATH` | `./attachments` | Local attachment storage |
| `LOG_LEVEL` | `INFO` | Logging level |

**Behaviour change:** starting or cancelling a scrape (`POST /api/scrape/start` and
`/api/scrape/cancel`, including from the portal's Archive screen) now requires `API_AUTH_TOKEN`,
sent as `Authorization: Bearer <token>`. If it is not set, those endpoints return `403` rather
than being open. Read-only endpoints are unchanged, and CORS no longer allows credentials,
arbitrary methods or arbitrary headers.

## UI / UX refresh proposal

A redesign of the portal (audit of the current UI, new information architecture, dark-theme tokens, components, desktop and mobile screens, motion spec) lives in [docs/UI_UX_PROPOSAL.md](docs/UI_UX_PROPOSAL.md) with the matching Figma file linked at the top of that document.

## Development

```bash
# Format + lint + type-check
make format && make lint

# Run tests
make test

# Run tests with coverage
make test-cov
```

## Security notes

- **Protect `.env`.** It holds live secrets (your Discord bot token). Never commit it, and restrict
  it to your user with `chmod 600 .env`. If a token is ever exposed (committed, pasted in a
  screenshot or log, or leaked in any other way), rotate it immediately in the Discord Developer
  Portal.
- **Keep the server on loopback.** `serve` and `dev` bind to `127.0.0.1` by default, and the API
  is unauthenticated for reads: anyone who can reach it can read the whole archive. Do not expose
  `serve` to the public internet or an untrusted network (for example with `--host 0.0.0.0`)
  without putting a reverse proxy with authentication in front of it.
- **Scrape control needs `API_AUTH_TOKEN`.** The endpoints that start or cancel a scrape (which
  use the server's Discord bot token) are only usable with this bearer token, and are disabled
  while it is unset. Pick a long random value, e.g.
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`, and send it over HTTPS if the
  server is reachable beyond your own machine. It does not protect the read endpoints.
- **The archive is private data.** The database and downloaded attachments contain private Discord
  messages, usernames, and files. Treat them like any other sensitive backup: restrict file
  permissions, keep them out of version control, and don't share them without consent.
- **Use a least-privilege bot token.** Invite the bot with only the permissions it needs (view
  channels and read message history) and enable only the gateway intents the archiver actually
  requires.

## License

MIT
