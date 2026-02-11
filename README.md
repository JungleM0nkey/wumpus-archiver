# Wumpus Archiver

A lightweight, self-hosted Discord server archival system with an exploration portal.

## Features

- **Complete Server Archival**: Scrape messages, channels, threads, users, attachments
- **Incremental Updates**: Resume from last position, update edited messages
- **Exploration Portal**: Discord-like web interface for browsing archives
- **Full-Text Search**: Search across all messages with filters
- **Data Visualization**: Activity timelines, user statistics, channel analytics
- **Export Options**: SQLite, JSON, HTML, CSV formats

## Quick Start

### Prerequisites

- Python 3.12+
- Discord Bot Token (see [Discord Developer Portal](https://discord.com/developers/applications))

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/wumpus-archiver.git
cd wumpus-archiver

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your tokens
```

### Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create New Application → Bot
3. Enable Privileged Intents:
   - MESSAGE CONTENT INTENT (required)
   - SERVER MEMBERS INTENT (recommended)
4. Copy Bot Token to `.env`
5. Invite bot to your server with permissions:
   - Read Messages/View Channels
   - Read Message History

### Usage

```bash
# Scrape a server
wumpus-archiver scrape --guild-id 123456789 --output ./my_archive.db

# Start exploration portal
wumpus-archiver serve ./my_archive.db --port 8080

# Update existing archive
wumpus-archiver update ./my_archive.db
```

## Architecture

```
Discord API (discord.py) → SQLite Database → FastAPI → SvelteKit Portal
```

## Documentation

- [Research Report](./docs/RESEARCH_REPORT.md) - Technical research findings
- [Architecture](./docs/ARCHITECTURE.md) - System design
- [Implementation Plan](./docs/IMPLEMENTATION_PLAN.md) - Development roadmap

## Tech Stack

- **Backend**: Python 3.12, discord.py, FastAPI, SQLAlchemy 2.0
- **Database**: SQLite (default), PostgreSQL (optional)
- **Frontend**: SvelteKit, TypeScript, Tailwind CSS
- **Search**: SQLite FTS5, FlexSearch

## License

MIT License - See LICENSE file

## Acknowledgments

- Inspired by [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter)
