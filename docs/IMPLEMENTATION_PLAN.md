# Wumpus Archiver - Implementation Plan

## Phase 1: Core Scraper (Weeks 1-2)

### Week 1: Project Setup & Bot Foundation

**Day 1-2: Project Structure**
```bash
wumpus-archiver/
├── pyproject.toml
├── wumpus_archiver/
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   ├── bot/
│   ├── storage/
│   └── utils/
└── tests/
```

**Day 3-4: Database Models**
- Set up SQLAlchemy 2.0 with async support
- Create models: Guild, Channel, Message, User, Attachment, Reaction
- Implement SQLite FTS5 virtual table for search
- Create Alembic migrations

**Day 5-7: Discord Bot Client**
- Implement `ArchiverBot` class with discord.py
- Configure intents (MESSAGE_CONTENT required)
- Add basic commands: `!archive`, `!status`
- Implement connection handling and error recovery

### Week 2: Scraping Logic

**Day 8-10: Message Fetching**
- Implement pagination with `before`/`after` cursors
- Handle rate limits with proper backoff
- Batch insert messages (1000 at a time)
- Track progress per channel

**Day 11-12: Attachment Handling**
- Download attachment files
- Hash-based deduplication
- Store local paths in database
- Progress tracking for large files

**Day 13-14: Incremental Updates**
- Store `last_scraped_at` timestamps
- Resume from last position
- Update edited messages
- Handle deleted messages (optional)

## Phase 2: Storage & API (Weeks 3-4)

### Week 3: Repository Pattern & API

**Day 15-17: Repository Layer**
```python
class MessageRepository:
    async def get_messages(channel_id, cursor, limit)
    async def search_messages(query, guild_id, filters)
    async def get_statistics(guild_id)
    async def upsert_guild(guild_data)
```

**Day 18-21: FastAPI Setup**
- Create FastAPI application
- Implement `/api/guilds`, `/api/channels`, `/api/messages`
- Add pagination with cursor-based navigation
- CORS configuration for portal

### Week 4: Background Jobs & Optimization

**Day 22-24: Background Processing**
- Implement `arq` for job queue
- Create `scrape_guild_task` for large servers
- Create `download_attachments_task`
- Add job status tracking

**Day 25-28: Performance**
- Connection pooling for database
- Batch processing optimization
- Memory profiling for large servers
- Caching layer for metadata

## Phase 3: Portal Foundation (Weeks 5-6)

### Week 5: Frontend Setup

**Day 29-31: SvelteKit Project**
```
portal/
├── src/
│   ├── routes/
│   │   ├── +layout.svelte
│   │   ├── +page.svelte
│   │   ├── guild/[id]/
│   │   ├── channel/[id]/
│   │   └── search/
│   ├── lib/
│   │   ├── components/
│   │   ├── stores/
│   │   └── api.ts
│   └── app.html
└── package.json
```

**Day 32-35: Core Components**
- Layout with Discord-like sidebar
- Channel list component
- Message list with virtual scrolling
- User avatar and mention components

### Week 6: UI Features

**Day 36-38: Navigation**
- Guild/channel routing
- Jump-to-date functionality
- Breadcrumb navigation
- Search input with filters

**Day 39-42: Message Display**
- Message rendering (text, embeds, attachments)
- Thread display (inline or panel)
- Reaction display
- Message actions (copy link, etc.)

## Phase 4: Advanced Features (Weeks 7-8)

### Week 7: Search & Visualization

**Day 43-45: Full-Text Search**
- Implement SQLite FTS5 queries
- Client-side search with FlexSearch
- Search filters (date, channel, user)
- Search result highlighting

**Day 46-49: Analytics**
- Message activity timeline (ECharts)
- User contribution statistics
- Channel activity heatmap
- Word frequency analysis

### Week 8: Export & Integration

**Day 50-52: Export Formats**
- JSON Lines exporter
- Static HTML generator
- CSV export for analysis
- Markdown export

## Testing Strategy

### Unit Tests
- Model serialization
- Repository queries
- Rate limiter logic

### Integration Tests
- Discord API mocking
- Database operations
- API endpoint testing

### Load Tests
- Large message batch processing
- Virtual scrolling performance
- Search query performance

## Deployment Checklist

- [ ] Environment variables configured
- [ ] Database migrations run
- [ ] Discord bot token secured
- [ ] Static files built
- [ ] Health checks implemented
- [ ] Logging configured
- [ ] Backup strategy defined
