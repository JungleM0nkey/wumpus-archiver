# Channel-Level Scraping — Frontend Implementation Guide

## Overview

The backend now supports scraping **individual channels** in addition to full-guild scrapes. This document describes the new API endpoints, data models, and provides detailed UI/UX specifications for extending the Control Panel (`/control`) to support channel selection.

---

## New Backend API

### 1. List Scrapeable Channels

```
GET /api/scrape/guilds/{guild_id}/channels
```

Returns all previously-scraped channels from the database for the given guild, grouped by category. Categories themselves are excluded from the list.

**Response:**
```json
{
  "guild_id": 165682173540696064,
  "guild_name": "My Server",
  "channels": [
    {
      "id": 165682173540696065,
      "name": "general",
      "type": 0,
      "type_name": "Text",
      "parent_name": "Main",
      "position": 0,
      "already_scraped": true,
      "archived_message_count": 12450
    },
    {
      "id": 165682173540696066,
      "name": "voice-chat",
      "type": 2,
      "type_name": "Voice",
      "parent_name": "Main",
      "position": 1,
      "already_scraped": false,
      "archived_message_count": 0
    }
  ],
  "total": 25
}
```

**Error (404):** If no channels found for the guild:
```json
{ "error": "No channels found for guild 123. Scrape the guild first." }
```

### 2. Start Scrape (Updated)

```
POST /api/scrape/start
```

**Request body now accepts `channel_ids`:**
```json
{
  "guild_id": 165682173540696064,
  "channel_ids": [165682173540696065, 165682173540696066]
}
```

- `channel_ids: null` or omitted → full guild scrape (existing behavior)
- `channel_ids: [...]` → scrape only specified channels

**Response:** Same `ScrapeJob` structure, with two new fields:
```json
{
  "job": {
    "id": "a1b2c3d4e5f6",
    "guild_id": 165682173540696064,
    "channel_ids": [165682173540696065, 165682173540696066],
    "scope": "channels",
    "status": "pending",
    "progress": { ... },
    ...
  }
}
```

### 3. Scrape Status / History (Updated)

`GET /api/scrape/status` and `GET /api/scrape/history` now return jobs with:
- `channel_ids: list[int] | null` — which channels were targeted (null = full guild)
- `scope: "guild" | "channels"` — quick indicator of scrape type

---

## TypeScript Types to Add

Add to `portal/src/lib/types.ts`:

```typescript
// Channel available for selective scraping
export interface ScrapeableChannel {
  id: number;
  name: string;
  type: number;
  type_name: string;
  parent_name: string | null;
  position: number;
  already_scraped: boolean;
  archived_message_count: number;
}

export interface ScrapeableChannelsResponse {
  guild_id: number;
  guild_name: string;
  channels: ScrapeableChannel[];
  total: number;
}
```

Update `ScrapeJob` interface:
```typescript
export interface ScrapeJob {
  id: string;
  guild_id: number;
  channel_ids: number[] | null;  // NEW
  scope: 'guild' | 'channels';  // NEW
  status: 'pending' | 'connecting' | 'scraping' | 'completed' | 'failed' | 'cancelled';
  progress: ScrapeProgress;
  started_at: string | null;
  completed_at: string | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  duration_seconds: number | null;
}
```

---

## API Client Functions to Add

Add to `portal/src/lib/api.ts`:

```typescript
export async function getScrapeableChannels(
  guildId: string | number
): Promise<ScrapeableChannelsResponse> {
  return fetchJSON<ScrapeableChannelsResponse>(`/scrape/guilds/${guildId}/channels`);
}
```

Update `startScrape`:
```typescript
export async function startScrape(
  guildId: number,
  channelIds?: number[]
): Promise<{ job: ScrapeJob }> {
  return fetchJSON<{ job: ScrapeJob }>('/scrape/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      guild_id: guildId,
      channel_ids: channelIds ?? null
    })
  });
}
```

---

## UI/UX Design Specification

### Design Philosophy

Follow the existing archive-dark design system. Use CSS custom properties (`--accent`, `--bg-surface`, `--border`, etc.), `mono` class for IDs/numbers, and the same card/section patterns already in the control panel.

### Layout Changes to Start Scrape Card

The existing "Start Scrape" card gets a **scrape mode toggle** and a **channel selector** that appears in "Select Channels" mode.

#### A. Scrape Mode Toggle

Below the guild selector, add a toggle between two modes:

```
┌─────────────────────────────────────────┐
│ ▶ Start Scrape                          │
├─────────────────────────────────────────┤
│ GUILD                                   │
│ [▼ My Server (165682173540696064)    ]  │
│                                         │
│ OR ENTER GUILD ID                       │
│ [___________________________________ ]  │
│                                         │
│ SCRAPE MODE                             │
│ ┌──────────────┬──────────────────────┐ │
│ │ ● Full Guild │ ○ Select Channels   │ │
│ └──────────────┴──────────────────────┘ │
│                                         │
│               [▶ Start Scrape]          │
└─────────────────────────────────────────┘
```

**Implementation:**
- Two-segment toggle (not a dropdown) using radio-style buttons
- Styling: `var(--bg-raised)` background, `var(--accent)` for active segment
- Default: "Full Guild" selected
- `disabled` when `isBusy` or `!hasToken`

#### B. Channel Selector (appears when "Select Channels" is active)

When "Select Channels" mode is chosen, show a channel list below the toggle:

```
┌─────────────────────────────────────────┐
│ CHANNELS (25 available)        [⟳ Load] │
│ ┌─────────────────────────────────────┐ │
│ │ [Select all] [Deselect all]   🔍    │ │
│ │                                     │ │
│ │ ▸ Main                              │ │
│ │   ☑ # general     12,450 msgs       │ │
│ │   ☑ # off-topic    3,200 msgs       │ │
│ │   ☐ # announcements   890 msgs      │ │
│ │                                     │ │
│ │ ▸ Voice                             │ │
│ │   ☐ 🔊 voice-chat       0 msgs      │ │
│ │   ☐ 🔊 music-bot        0 msgs      │ │
│ │                                     │ │
│ │ ▸ (no category)                     │ │
│ │   ☐ # random         1,560 msgs     │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ 2 channels selected                     │
│                                         │
│           [▶ Scrape 2 Channels]         │
└─────────────────────────────────────────┘
```

**Implementation Details:**

1. **Loading Channels:**
   - When "Select Channels" mode is activated, call `getScrapeableChannels(guildId)`
   - Show a loading spinner in the channel list while fetching
   - If the guild hasn't been scraped yet, show a message: "Scrape the guild once first to populate the channel list."
   - Cache the result per guild ID to avoid refetching on toggle

2. **Channel List:**
   - Group channels by `parent_name` (category), with `null` → "(no category)"
   - Show category names as collapsible group headers (click to expand/collapse, all expanded by default)
   - Each channel row: checkbox + channel icon (# for text, 🔊 for voice, 📢 for announcement, 🧵 for thread, 📋 for forum) + name + message count (right-aligned, muted, mono)
   - Channel icon based on `type`: `0` → #, `2` → 🔊, `5` → 📢, `11/12` → 🧵, `13` → 🎙️, `15` → 📋
   - Channels with `already_scraped: true` could have a subtle indicator (e.g., small dot or different row background)

3. **Toolbar:**
   - "Select all" / "Deselect all" text buttons (links, not full buttons)
   - Optional: filter/search input to filter channels by name
   - Counter: "N channels selected" below the list

4. **Button Text Updates:**
   - Full Guild mode: "▶ Start Scrape"
   - Channel mode, 0 selected: "▶ Start Scrape" (disabled)
   - Channel mode, N selected: "▶ Scrape N Channel(s)"

5. **Styling:**
   - Channel list container: `var(--bg-raised)` background, `var(--border)` border, `var(--radius-md)` corners
   - Max height: 300px with `overflow-y: auto`
   - Checkboxes: style with accent color (`var(--accent)`)
   - Category headers: `font-size: 12px`, `text-transform: uppercase`, `color: var(--text-muted)`, `letter-spacing: 0.04em`, left padding with a small collapse arrow
   - Channel rows: `padding: var(--sp-2) var(--sp-3)`, hover with `var(--bg-hover)`

### C. Live Status Card Updates

When a channel-scoped job is running, the Live Status card should reflect this:

1. **Scope indicator:** Show "Scope: 2 channels" or "Scope: Full guild" in the status grid
2. **Progress context:** The "Channel" field already shows `current_channel` — no change needed
3. **Channel progress:** If `channel_ids` is set, show "2/5 channels" progress in addition to messages

```
┌─────────────────────────────────────────┐
│ ◉ Live Status               ◉ SCRAPING │
├─────────────────────────────────────────┤
│ JOB ID     a1b2c3d4e5f6                │
│ GUILD      165682173540696064           │
│ SCOPE      3 channels                  │  ← NEW
│ CHANNEL    #general                    │
│ DURATION   1m 23s                      │
│                                         │
│   ┌───────┬──────────┬────────────┐    │
│   │  2    │  4,521   │    312     │    │
│   │ chans │ messages │ attachments│    │
│   └───────┴──────────┴────────────┘    │
│                                         │
│  ▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░    │
└─────────────────────────────────────────┘
```

### D. History Table Updates

Add a "Scope" column to the history table:

| Status | Job ID | Guild | Scope | Channels | Messages | Attachments | Duration | Started |
|--------|--------|-------|-------|----------|----------|-------------|----------|---------|
| ✓ completed | a1b2c3 | 1656... | 3 channels | 3 | 15,234 | 892 | 2m 15s | Feb 11... |
| ✓ completed | d4e5f6 | 1656... | Full guild | 25 | 45,000 | 3,201 | 12m 3s | Feb 10... |

**Implementation:**
- New column after "Guild"
- Value: `job.scope === 'channels' ? `${job.channel_ids?.length} channel(s)` : 'Full guild'`
- Style the "Full guild" text in `var(--text-muted)` and channel counts in normal text

---

## State Management

New state variables to add to the control panel component:

```typescript
// Scrape mode
let scrapeMode: 'guild' | 'channels' = $state('guild');

// Channel selection
let scrapeableChannels: ScrapeableChannel[] = $state([]);
let selectedChannelIds: Set<number> = $state(new Set());
let channelsLoading = $state(false);
let channelsError = $state('');
let channelsLoadedForGuild = $state('');  // cache key
```

### Key Behaviors

1. **Mode switching:** When toggling from "channels" back to "guild", preserve the channel selection (don't clear it). The user may toggle back.

2. **Guild change:** When the selected guild changes and mode is "channels", clear the channel cache and reload:
   ```typescript
   $effect(() => {
     const gid = resolvedGuildId();
     if (gid && scrapeMode === 'channels' && String(gid) !== channelsLoadedForGuild) {
       loadChannels(gid);
     }
   });
   ```

3. **Start action:** Update `handleStart` to pass channel IDs when in channels mode:
   ```typescript
   async function handleStart() {
     const gid = resolvedGuildId();
     if (!gid) return;

     if (scrapeMode === 'channels' && selectedChannelIds.size > 0) {
       await startScrape(gid, Array.from(selectedChannelIds));
     } else if (scrapeMode === 'guild') {
       await startScrape(gid);
     }
   }
   ```

4. **Validation:** In channels mode, disable the start button when no channels are selected.

---

## Edge Cases to Handle

1. **Guild not yet scraped:** `getScrapeableChannels` returns 404 → show inline message: "This guild hasn't been scraped yet. Run a full guild scrape first to populate the channel list."

2. **Empty channel list:** Could happen if guild only has categories. Show: "No scrapeable channels found."

3. **Large channel counts (100+):** The channel list should be scrollable (max-height: 300px). Add a search filter if there are >20 channels.

4. **Job already running:** Same behavior as before — disable the start button and show the cancel button.

5. **Channel deleted from Discord:** The scraper will report an error for that channel ID in `progress.errors`. Display normally in the errors section.

---

## File Changes Summary

| File | Changes |
|------|---------|
| `portal/src/lib/types.ts` | Add `ScrapeableChannel`, `ScrapeableChannelsResponse`. Update `ScrapeJob` with `channel_ids`, `scope`. |
| `portal/src/lib/api.ts` | Add `getScrapeableChannels()`. Update `startScrape()` signature to accept optional `channelIds`. |
| `portal/src/routes/control/+page.svelte` | Add mode toggle, channel selector, update start handler, update status display, update history table. |

---

## Testing Checklist

- [ ] Full guild scrape still works unchanged when mode is "Full Guild"
- [ ] Switching to "Select Channels" loads the channel list for the selected guild
- [ ] Changing guild reloads the channel list
- [ ] Select all / Deselect all work correctly
- [ ] Start button shows correct text ("Start Scrape" vs "Scrape N Channel(s)")
- [ ] Start button is disabled in channel mode with 0 channels selected
- [ ] Channel-scoped job shows "Scope: N channels" in live status
- [ ] History table shows scope column correctly
- [ ] 404 from channel list endpoint shows friendly message
- [ ] Polling continues to work during channel-scoped scrapes
- [ ] Cancel works for channel-scoped scrapes
