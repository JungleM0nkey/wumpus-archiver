# Wumpus Archiver - AI Assistant Context

## Project Overview

Wumpus Archiver is a Discord server archival system with an exploration portal. It scrapes Discord server history and provides a web interface for browsing archives.

**Current State**: Phase 1 complete - Core scraper implemented with SQLAlchemy models, repository pattern, and CLI.

> See also: `.github/copilot-instructions.md` for concise coding guidelines shared across AI agents.

## Project Structure

```
wumpus-archiver/
├── src/                    # Source code (Phase 1 implemented)
│   └── wumpus_archiver/
│       ├── __init__.py
│       ├── config.py          # Pydantic settings management
│       ├── cli.py             # Click CLI interface
│       ├── models/            # SQLAlchemy 2.0 models
│       │   ├── base.py
│       │   ├── guild.py
│       │   ├── channel.py
│       │   ├── user.py
│       │   ├── message.py
│       │   ├── attachment.py
│       │   └── reaction.py
│       ├── bot/               # Discord bot scraper
│       │   └── scraper.py
│       ├── storage/           # Repository pattern
│       │   ├── database.py
│       │   └── repositories.py
│       ├── api/               # FastAPI (Phase 2 - TODO)
│       └── utils/             # Utilities
├── tests/                  # Test files (TODO)
├── scripts/                # Utility scripts (TODO)
├── docs/                   # Documentation
├── README.md
├── CLAUDE.md
├── LICENSE
├── pyproject.toml
└── .env.example
```

## Key Decisions

### Tech Stack
- **Backend**: Python 3.12, discord.py, FastAPI, SQLAlchemy 2.0
- **Database**: SQLite (default), PostgreSQL (optional)
- **Frontend**: SvelteKit, TypeScript, Tailwind CSS (Phase 3)
- **Search**: SQLite FTS5, FlexSearch (Phase 4)

### Architecture Patterns
- Repository pattern for database operations
- Async/await throughout
- Pydantic settings for configuration
- Click for CLI interface

### Scope Decisions
- **NO Firecrawl integration** - removed from roadmap
- **NO MCP integration for core scraper** - using discord.py directly
- Focus on core archival functionality first
- MCP may be added later for archive querying (read-only)

## Implementation Status

### Phase 1: Core Scraper ✓ COMPLETE
- [x] Project structure and pyproject.toml
- [x] SQLAlchemy 2.0 models (Guild, Channel, User, Message, Attachment, Reaction)
- [x] Database layer with async support
- [x] Repository pattern (Guild, Channel, Message, User, Attachment, Reaction)
- [x] Discord bot scraper (ArchiverBot) with pagination
- [x] CLI interface (scrape, serve, update, init commands)
- [x] Configuration management with Pydantic

### Phase 2: Storage & API (TODO)
- [ ] FastAPI application
- [ ] REST API endpoints
- [ ] CORS configuration
- [ ] Background job queue (arq)

### Phase 3: Portal Foundation (TODO)
- [ ] SvelteKit project setup
- [ ] Discord-like UI components
- [ ] Virtual scrolling for messages
- [ ] Channel/guild navigation

### Phase 4: Advanced Features (TODO)
- [ ] Full-text search (FTS5)
- [ ] Analytics and visualizations
- [ ] Export formats (JSON, HTML, CSV)
- [ ] Attachment download management

## Development Guidelines

### Code Organization
Models use SQLAlchemy 2.0 style with `Mapped[]` and `mapped_column()`.

### Adding a New Model
1. Create model in `src/wumpus_archiver/models/`
2. Import in `models/__init__.py`
3. Create repository in `storage/repositories.py`
4. Add to database creation in `database.py`
5. Update bot scraper to save the model

### Repository Pattern
All database access goes through repositories:
- `GuildRepository` - Guild CRUD operations
- `ChannelRepository` - Channel CRUD operations
- `MessageRepository` - Message CRUD with pagination
- `UserRepository` - User CRUD operations
- `AttachmentRepository` - Attachment tracking
- `ReactionRepository` - Reaction aggregation

## Usage

### Setup
```bash
# Install dependencies
pip install -e ".[dev]"

# Initialize project
wumpus-archiver init
# Edit .env with your Discord bot token
```

### Scrape a Server
```bash
wumpus-archiver scrape --guild-id 123456789 --output ./my_archive.db
```

### Start Portal (Phase 2+)
```bash
wumpus-archiver serve ./my_archive.db --port 8080
```

## Environment Variables

See `.env.example` for all options.

Key variables:
- `DISCORD_BOT_TOKEN` - Required for Discord API access
- `DATABASE_URL` - Database connection string
- `BATCH_SIZE`/`RATE_LIMIT_DELAY` - Scraping configuration
- `DOWNLOAD_ATTACHMENTS` - Whether to download attachments

## Known Issues / TODOs

1. ~17 source files created but not yet tested
2. No test suite implemented
3. No API layer (Phase 2)
4. No web portal (Phase 3)
5. Attachment download not implemented
6. Incremental updates not implemented

## Resources

- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
- [Click Documentation](https://click.palletsprojects.com/)
