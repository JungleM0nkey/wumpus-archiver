# Roadmap: Merge Gallery into Channels

## Problem

The **Gallery** (`/gallery`) and **Channels** (`/channels`) pages overlap in purpose — both let users browse archived content organized by channel. Gallery adds media browsing (grid/timeline views with lightbox), while Channels is just a listing page that links to individual channel views. Having both as separate top-level nav items creates confusion and dilutes the experience.

## Goal

Merge gallery functionality **into** the channel views, creating a unified "Channels" experience with tabbed content modes. Remove the standalone `/gallery` route and nav link.

---

## Architecture Overview

### Current State

```
/channels          → Channel listing grid (cards with message counts)
/channel/[id]      → Messages feed (TimelineFeed component)
/gallery           → Standalone media browser (sidebar + grid/timeline view + lightbox)
```

### Target State

```
/channels          → Channel listing grid (cards with message counts + media preview)
/channel/[id]      → Tabbed view: Messages | Gallery
                     └── Messages tab: existing TimelineFeed
                     └── Gallery tab: grid/timeline media view (from gallery page)
```

---

## Tasks

### Phase 1: Build Channel Gallery Tab Component

**File: `portal/src/lib/components/ChannelGallery.svelte`** (new)

Extract the gallery functionality from `/gallery/+page.svelte` into a reusable component that works for a single channel.

- [ ] **1.1** Create `ChannelGallery.svelte` component
  - Props: `channelId: string`, `guildId: string`
  - Internal state: view mode (grid/timeline), group-by selector, attachments, pagination
  - Reuses existing `GalleryGrid.svelte` and `Lightbox.svelte` components
  - Calls `getGuildGallery()` and `getGuildGalleryTimeline()` with `channel_id` filter
  - Includes the view mode toggle (grid/timeline) and group-by pills from the gallery sidebar
  - Includes timeline view markup currently in `/gallery/+page.svelte` lines 290-350

- [ ] **1.2** Create `ChannelGallery` toolbar
  - View toggle: Grid | Timeline (compact inline toggle, not sidebar)
  - Group-by pills: week | month | year (shown only in timeline mode)
  - Item count display
  - All inline in a toolbar row above the content — no sidebar needed for single-channel context

### Phase 2: Add Tabbed Navigation to Channel Detail Page

**File: `portal/src/routes/channel/[id]/+page.svelte`** (modify)

- [ ] **2.1** Add tab state and tab bar UI
  - Tabs: `Messages` | `Gallery`
  - Store active tab in `$state`, default to `'messages'`
  - Tab bar sits below the channel header, above the content area
  - Style tabs using existing design system tokens (similar to gallery's `.tab-group`)
  - Update the `gallery-link` (🖼 View Gallery) that currently points to a non-existent `/channel/{id}/gallery` route — replace with tab switch

- [ ] **2.2** Conditionally render content based on active tab
  - `messages` tab: existing `TimelineFeed` + load-more logic (no changes)
  - `gallery` tab: render `<ChannelGallery channelId={channelId} guildId={guildId} />`
  - Pass `guildId` — need to plumb it from the `loadChannel()` function which already fetches the guild

- [ ] **2.3** Support URL-driven tab selection
  - Use query param `?tab=gallery` to allow deep-linking to gallery tab
  - Read from `page.url.searchParams` on mount
  - Update URL when switching tabs via `goto()` with `replaceState`

### Phase 3: Enhance Channel Listing with Media Previews (Optional Polish)

**File: `portal/src/routes/channels/+page.svelte`** (modify)

- [ ] **3.1** Add thumbnail previews to channel cards
  - Fetch 1-3 recent gallery attachments per channel for preview thumbnails
  - Show small image strip at bottom of each channel card
  - Requires new API endpoint or batch gallery preview endpoint
  - *Can be deferred — nice-to-have polish*

### Phase 4: Remove Standalone Gallery Page

**Files to modify/delete:**

- [ ] **4.1** Remove gallery route
  - Delete `portal/src/routes/gallery/+page.svelte`
  - The per-channel gallery sidebar/filtering is no longer needed since gallery is scoped to a channel

- [ ] **4.2** Update navigation
  - Remove `{ href: '/gallery', label: 'Gallery', icon: '⊞' }` from `Nav.svelte` links array
  - This frees up nav space and reduces user confusion

- [ ] **4.3** Update any internal links to `/gallery`
  - Search for `href="/gallery"` or `href='/gallery'` references in all components/pages
  - Dashboard (`+page.svelte`) may have gallery links — redirect to channels

- [ ] **4.4** Redirect for bookmarks (optional)
  - Add a redirect in `portal/src/routes/gallery/+page.ts` that redirects `/gallery` → `/channels`
  - Or simply delete and let 404 handle it (SPA will show fallback)

### Phase 5: Cleanup & Polish

- [ ] **5.1** Review `GalleryGrid.svelte` and `Lightbox.svelte` — no changes needed, they're already reusable
- [ ] **5.2** Remove unused API functions if any (unlikely — `getGuildGallery` and `getGuildGalleryTimeline` are still used)
- [ ] **5.3** Consider adding a "guild-wide gallery" link somewhere (e.g., dashboard stat card or channels header) for users who want cross-channel media browsing — this preserves the original gallery's "all channels" filter but in a less prominent spot
- [ ] **5.4** Test all states: loading, empty (channel with no images), error, pagination, lightbox
- [ ] **5.5** Mobile responsiveness — ensure tab bar and gallery grid work well on small viewports

---

## Component Hierarchy (Target)

```
/channel/[id]/+page.svelte
├── Channel Header (name, topic, meta)
├── Tab Bar [Messages | Gallery]
├── Messages Tab (active by default)
│   └── TimelineFeed
│       └── MessageCard (per message)
└── Gallery Tab
    └── ChannelGallery
        ├── Toolbar (view toggle, group-by, count)
        ├── Grid View
        │   └── GalleryGrid
        │       └── Lightbox (overlay)
        └── Timeline View
            └── Timeline groups + Lightbox
```

## Files Changed Summary

| File | Action | Description |
|------|--------|-------------|
| `lib/components/ChannelGallery.svelte` | **Create** | Extracted single-channel gallery component |
| `routes/channel/[id]/+page.svelte` | **Modify** | Add tab bar + gallery tab |
| `routes/gallery/+page.svelte` | **Delete** | Remove standalone gallery page |
| `lib/components/Nav.svelte` | **Modify** | Remove gallery nav link |
| `routes/channels/+page.svelte` | **Modify** | (Optional) Add thumbnail previews |
| `routes/+page.svelte` | **Modify** | Update any gallery links on dashboard |

## Effort Estimate

| Phase | Effort | Priority |
|-------|--------|----------|
| Phase 1: ChannelGallery component | Medium | **P0** |
| Phase 2: Tabbed channel detail | Medium | **P0** |
| Phase 3: Channel listing previews | Small | P2 (optional) |
| Phase 4: Remove gallery page + nav | Small | **P0** |
| Phase 5: Cleanup & polish | Small | P1 |

**Total: ~2-3 hours of focused work for P0 tasks.**
