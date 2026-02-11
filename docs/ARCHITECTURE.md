# Wumpus Archiver - Architecture Document

## System Overview

The wumpus-archiver is a modular Discord server archival system with a clean separation between data collection, storage, and presentation layers.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Discord Bot    │────▶│  Data Storage    │────▶│  Web Portal     │
│  (discord.py)   │     │  (SQLite/PG)     │     │  (SvelteKit)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Component Breakdown

### 1. Discord Bot Module

**Purpose**: Authenticate with Discord and collect server data

**Key Classes:**
- `ArchiverBot` - Discord.py bot client
- `GuildScraper` - Orchestrates server scraping
- `ChannelScraper` - Handles per-channel message fetching
- `RateLimiter` - Respects Discord API limits

**Rate Limiting Strategy:**
- Parse `X-RateLimit-Remaining` header
- Sleep when approaching limits
- Exponential backoff on 429 errors
- Per-channel rate limit tracking

### 2. Storage Layer

**Purpose**: Abstract database operations

**Repository Pattern:**
```python
class MessageRepository:
    async def get_messages(channel_id, before, after, limit)
    async def search_messages(query, filters)
    async def insert_messages_batch(messages)
    async def get_statistics(guild_id)
```

**Database Schema:**
- Guilds, Channels, Threads
- Messages (with FTS5 index)
- Users, Attachments, Reactions
- ArchiveMetadata

### 3. API Layer

**Purpose**: Provide REST API for portal

**Endpoints:**
- `GET /api/guilds/{id}/channels` - List channels
- `GET /api/channels/{id}/messages` - Get messages
- `POST /api/search` - Full-text search
- `GET /api/guilds/{id}/statistics` - Analytics

### 4. Web Portal

**Purpose**: User interface for browsing archives

**Key Features:**
- Virtual scrolling for performance
- Client-side search (FlexSearch)
- Date-based navigation
- Media gallery with lazy loading

## Data Flow

### Scraping Flow
```
1. Bot authenticates with Discord
2. Fetch guild metadata
3. For each channel:
   a. Fetch message history (paginated)
   b. Download attachments
   c. Store in database
4. Update archive metadata
```

### Portal Query Flow
```
1. User requests channel messages
2. API queries repository
3. Repository hits database
4. Results returned with pagination
5. Portal renders with virtual scroll
```

## Scalability Considerations

| Scale | Messages | Storage | Approach |
|-------|----------|---------|----------|
| Small | <100K | <1GB | SQLite + client search |
| Medium | 100K-1M | 1-10GB | SQLite + server search |
| Large | 1M-10M | 10-100GB | PostgreSQL + Meilisearch |
| Enterprise | >10M | >100GB | Distributed deployment |

## Deployment Options

### Option 1: Desktop App (Recommended)
Single executable with embedded Python + web portal

### Option 2: Docker Compose
- FastAPI container
- PostgreSQL container (optional)
- Meilisearch container (optional)
- Static file serving

### Option 3: Serverless
- Cloud function for scraping
- Object storage for archives
- CDN for portal assets
