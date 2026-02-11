# Wumpus Archiver - Deep Research Report

## Executive Summary

This research covers the design and deployment of **wumpus-archiver**, a lightweight application stack for scraping Discord server history and building an exploration portal. The research was conducted using parallel subagents analyzing Discord API capabilities, application architecture, and exploration portal design.

**Key Finding**: The primary archival should use Discord API (discord.py) for reliable message scraping with proper rate limiting and authentication handling.

---

## 1. Discord API Research

### 1.1 API Endpoints Available

| Data Type | Endpoint | Limits |
|-----------|----------|--------|
| Guild Info | `GET /guilds/{id}` | Standard rate limits |
| Channels | `GET /guilds/{id}/channels` | 1000+ channels supported |
| Messages | `GET /channels/{id}/messages` | **100 per request** |
| Members | `GET /guilds/{id}/members` | **1000 per request** |
| Threads | `GET /channels/{id}/threads/archived/*` | Pagination required |
| Reactions | `GET /channels/{id}/messages/{id}/reactions/{emoji}` | Per-message |

### 1.2 Rate Limits

| Limit Type | Value | Notes |
|------------|-------|-------|
| Global Bot | 50 req/sec | Across all endpoints |
| Channel Messages | ~5 req/5 sec | Per channel |
| Bulk Delete | 2 weeks max | Only recent messages |

### 1.3 Required Permissions & Intents

**Required Bot Permissions:**
- `VIEW_CHANNEL` (0x400)
- `READ_MESSAGE_HISTORY` (0x10000)

**Privileged Intents (require verification for 100+ guilds):**
- `MESSAGE_CONTENT` - **Required** to read message text, embeds, attachments
- `GUILD_MEMBERS` - For member list scraping

### 1.4 Historical Data Access

- **No time limit** on message history
- ~100 messages per request means 1M messages = ~10,000 API calls

---

## 2. Recommended Architecture

**Stack:**
- **Backend**: Python 3.12 + discord.py + FastAPI + SQLAlchemy 2.0
- **Database**: SQLite (default) with PostgreSQL option for scale
- **Frontend**: SvelteKit + Tailwind CSS + shadcn/ui
- **Search**: FlexSearch/MiniSearch (client-side) or Meilisearch (server)

---

## 3. Implementation Roadmap

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| 1. Core Scraper | Weeks 1-2 | Discord bot, database, pagination |
| 2. Storage & API | Weeks 3-4 | Repository pattern, FastAPI, attachments |
| 3. Portal Foundation | Weeks 5-6 | SvelteKit UI, virtual scrolling |
| 4. Advanced Features | Weeks 7-8 | Search, visualization, export formats |

---

## Key Recommendations

1. Use Discord API for all archival operations
2. Start with SQLite - single file portability
3. Implement virtual scrolling early
4. Design for incremental updates from the start
5. Use client-side search for archives <500K messages

---

*Research conducted: 2026-02-10 using parallel subagent exploration*
