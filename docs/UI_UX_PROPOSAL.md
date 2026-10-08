# Wumpus Archiver — UI / UX refresh proposal

**Figma file:** https://www.figma.com/design/taRjQBSRc6HKWPaaIkiikm
(pages: `00 Cover`, `01 Audit — Current State`, `02 Foundations`, `03 Components`, `04 Screens — Desktop`, `05 Screens — Mobile`, `06 Motion & Interaction`)

This document is the written companion to the Figma file. It records what the
current SvelteKit portal does today, what the refreshed design proposes, the token
and motion system it is built on, and an implementation order that lets the work
land in reviewable pieces.

---

## 1. Audit of the current portal

Read from `portal/src/**` and `src/wumpus_archiver/api/routes/*`.

### Broken

| # | Finding | Where |
|---|---|---|
| 1 | **Every page renders twice.** `{@render children()}` is called inside `<main>` and again after the `<style>` block, so each route mounts twice and every `onMount` fetch fires twice. | `portal/src/routes/+layout.svelte` |
| 2 | **"Load older messages" loads newer ones.** The messages endpoint orders ascending and the button passes `after=lastId`. The reader opens at the oldest message and walks forward; `has_more` starts as `true`. | `channel/[id]/+page.svelte`, `timeline/+page.svelte`, `api/routes/messages.py` |
| 3 | **Profile "Recent messages" double-fetches and 422s.** `searchMessages('')` is rejected by `min_length=1`; a second raw fetch with `q=' '` follows, errors swallowed. | `users/[id]/+page.svelte` |
| 4 | **People ranks drift after Load more.** `i + 1 + offset - users.length + users.length`, with `offset` advanced before the fetch. | `users/+page.svelte` |
| 5 | **Dashboard top channels link to `/channels`, not the channel.** `stats.top_channels` carries names only. | `routes/+page.svelte`, `api/routes/stats.py` |
| 6 | **Control page polls every 2 s forever**, idle or not, and re-fetches history on every idle tick. | `control/+page.svelte` |
| 7 | **Multi-guild archives are invisible.** Every route resolves `getGuilds()[0]`; there is no switcher. | all routes |

### Redundant

| # | Finding | Where |
|---|---|---|
| 8 | **Three routes browse channel messages**: `/channels` (card grid), `/timeline` (sidebar + feed), `/channel/[id]` (feed + header). `/timeline` even lists voice channels. | `channels`, `timeline`, `channel/[id]` |
| 9 | **Two galleries, two lightboxes.** `/gallery` already filters by channel yet `/channel/[id]/gallery` exists; the gallery's timeline mode re-implements thumbnails and owns its own `Lightbox` state while `GalleryGrid` owns another. | `gallery`, `channel/[id]/gallery`, `GalleryGrid.svelte` |
| 10 | **Shared styles copy-pasted ten times.** `.spinner`, `@keyframes spin`, `.center-state`, `.dot` and three different load-more buttons are re-declared per page. | every `+page.svelte` |
| 11 | **Counts derived twice.** The channels page looks up counts by name in `stats.top_channels` although `Channel.message_count` is on the row. | `channels/+page.svelte` |

### Inconsistent

| # | Finding | Where |
|---|---|---|
| 12 | **Three icon systems**: Unicode glyphs (◈ ▤ ⌕ ≡ ⊞ ◉ ⚙), emoji (📌 📎 🖼 🔊 🎭) and inline SVG. Rendering depends on the OS font. | `Nav.svelte`, `MessageCard.svelte`, `timeline` |
| 13 | **Three typefaces, one motif.** Space Grotesk, JetBrains Mono and Source Serif 4 all load; the serif is only used for "Title." headings with an amber dot repeated on six pages. | `global.css`, page headers |
| 14 | **Scroll model changes per page.** Four pages scroll the shell, four nest their own scroll area. Sticky headers and scroll restoration differ. | `+layout.svelte`, page roots |
| 15 | **Nothing responds below 768 px.** The top nav never collapses; sidebars are `display:none`, which removes the gallery channel filter. | `Nav.svelte`, `gallery`, `timeline` |
| 16 | **Message cards print raw snowflake IDs** in a footer, replies show a "↩ reply" badge with no context, consecutive messages never group. | `MessageCard.svelte` |
| 17 | **Search is thinner than the API**: `author_id` is supported server-side but not exposed; no date or `has:` filters; "AI semantic search coming soon" placeholder text. | `search/+page.svelte` |
| 18 | **Scaffold leftovers**: the favicon is the SvelteKit logo, the version badge is hardcoded `v0.1.0`. | `favicon.svg`, `Nav.svelte` |

---

## 2. Proposed information architecture

Seven top-level destinations become five, plus **Archive & jobs** reachable from
the sidebar footer. Nothing is dropped; each old route maps to a view or a tab.

| Today | Proposed | What changes |
|---|---|---|
| `/` Dashboard | `/` **Overview** | Activity-over-time chart, archive health row, guild switcher. Stat tiles show the delta since the last scrape. |
| `/channels` · `/timeline` · `/channel/[id]` | `/browse/[channel]` **Browse** | One three-pane reader: channel pane grouped by category, message feed with grouped authors and sticky date pills, jump-to-date rail. Pagination goes backwards in time. |
| `/gallery` · `/channel/[id]/gallery` · `/timeline` (media) | `/media` **Media** + a Media tab inside Browse | One justified grid grouped by month with sticky headers. Channel and type are filters, not routes. One lightbox with filmstrip and "Open in conversation". |
| `/search` | `/search` **Search** + ⌘K palette | Filter chips (`in:`, `from:`, `has:`, date), highlighted snippets, facets, jump-to-context. The palette is reachable from every screen. |
| `/users` · `/users/[id]` | `/people` · `/people/[id]` **People** | Directory becomes a sortable table; profile gains a 52-week activity heatmap and reaction stats. |
| `/control` | `/archive` **Archive & jobs** | Leaves the primary nav. Scrape health lives in the sidebar footer; the page keeps jobs, downloads and history and only polls while a job runs. |

**Shell.** A persistent 240 px left sidebar (collapsible to a 64 px icon rail with
`⌘\`) replaces the top nav. It holds the brand, a guild switcher, search (`⌘K`),
the five destinations, and an archive-status card. Below 768 px the sidebar
becomes a sheet and a bottom tab bar carries the five destinations.

---

## 3. Design language

**Direction: a dark reading room.** Near-black warm neutrals, one amber accent used
sparingly as "ink", a mono face for anything numeric. No gradients on surfaces, no
glass, no purple. Depth comes from lighter surfaces, not shadows; shadows exist
only for floating elements.

### Color tokens (Theme / Dark)

All values are Figma variables with `var(--…)` code syntax. Semantic tokens alias
a `Primitives` collection (`ink/50…950`, `amber/300…600`, status hues).

| Token | Value | CSS |
|---|---|---|
| `bg/canvas` | `#0A0A0C` | `--bg-canvas` |
| `bg/surface` | `#0F0F12` | `--bg-surface` |
| `bg/raised` | `#141418` | `--bg-raised` |
| `bg/overlay` | `#1A1A1F` | `--bg-overlay` |
| `bg/inset` | `#202027` | `--bg-inset` |
| `bg/hover` / `bg/active` | white 5 % / 8 % | `--bg-hover`, `--bg-active` |
| `border/subtle` / `default` / `strong` | white 7 % / 12 % / 22 % | `--border-*` |
| `text/primary` | `#EFEDE8` | `--text-primary` |
| `text/secondary` | `#8F8F9B` | `--text-secondary` |
| `text/tertiary` | `#6B6B78` | `--text-tertiary` |
| `accent/default` | `#F0B254` | `--accent` |
| `accent/strong` | `#E59A2D` | `--accent-strong` |
| `accent/muted` / `glow` | amber 12 % / 22 % | `--accent-muted`, `--accent-glow` |
| `status/success` · `danger` · `warning` · `info` | `#5BD38A` · `#F0665C` · `#F2C14E` · `#7EB2F5` | `--success` … |

### Typography

**Instrument Sans** for UI, **JetBrains Mono** for timestamps, IDs and counts
(tabular numerals). Space Grotesk and Source Serif are retired.

| Style | Spec |
|---|---|
| `display/xl` · `display/lg` | 44/48 · 32/38, SemiBold, −2.5 % / −2 % |
| `heading/lg` · `md` · `sm` | 22/28 · 17/24 · 15/20, SemiBold |
| `body/md` · `body/sm` | 14/22 · 13/18, Regular |
| `label/md` · `sm` · `xs` | 13/16 · 12/16 · 11/14, Medium |
| `caption` | 11/14, Medium, uppercase, +6 % tracking |
| `mono/md` · `mono/sm` | 13/18 · 11/14 |
| `mono/num-lg` · `num-xl` | 28/32 · 40/44, Medium |

### Spacing, radius, size

`space/1…16` = 4, 8, 12, 16, 20, 24, 32, 40, 48, 64.
`radius/xs…xl` = 4, 6, 10, 14, 20; `radius/full` = 999.
`size/sidebar` 240, `size/rail` 64, `size/topbar` 56, `size/reader-max` 880.

### Iconography

One set: 20 px stroke icons at 1.75 px (Lucide-compatible), instanced and
resized to 16/18/20. Icon strokes bind to `text/secondary` and are recolored per
state. Emoji are used only for reactions.

---

## 4. Screens

All desktop screens are 1440 wide; pages that scroll are shown at their full
content height. Mobile screens are 390 × 844.

- **Overview.** Guild hero, four stat tiles with deltas, messages-per-month area
  chart, most-active channels and top contributors side by side, and an archive
  health card (download progress, last job, token status) that links to Archive.
- **Browse.** Channel pane (filter, categories, counts) · reader (title, topic,
  Messages / Media / Pinned tabs, grouped messages with hover actions, sticky
  date pills, "Newest messages" jump pill) · jump rail (years, months, channel
  facts, keyboard hints).
- **Search.** Query bar with Clear/Search, filter chips, result count and sort,
  result rows with the match highlighted in accent and "Open in context" on
  hover, and a refine rail with channel/person facets and a date histogram.
- **Media.** Type chips, channel and sort selects, grid/list toggle, sticky month
  headers, justified rows of natural-aspect tiles with video and GIF badges.
  **Lightbox:** author and counter in the top bar, centered image, prev/next,
  filmstrip, file metadata, "Open in conversation".
- **People.** Search, segmented sort, summary line, a table with rank, avatar,
  name/handle, share bar, message count and active range.
- **Profile.** Breadcrumb, avatar and handle, four stat tiles, 52-week activity
  heatmap, top channels, reactions received, frequent words, recent messages.
- **Archive & jobs.** Info alert, "Run a scrape" form (server, scope, options),
  live job card (progress, current channel, counters, per-channel status,
  cancel), attachments-on-disk card with per-channel table, job history table.
- **Mobile.** Overview (2 × 2 tiles, chart, top channels), Browse channel list,
  Reader (full-screen with a bottom action bar), Media (3-column grid), Search.
  A bottom tab bar carries the five destinations.

---

## 5. Motion and interaction

Four durations, three curves. Motion explains where something came from; it
never decorates. Every animation collapses to a cross-fade under
`prefers-reduced-motion`.

| Token | Value | Used for |
|---|---|---|
| `duration/micro` | 120 ms, ease-out-quint | hover tint, press scale 0.98, chip toggle, icon color |
| `duration/small` | 180 ms, standard `(0.2, 0, 0, 1)` | toggles, tab indicator slide, badge swap, tooltip |
| `duration/medium` | 240 ms, ease-out-quint | panels, popovers, command palette, lightbox, content enter |
| `duration/large` | 320 ms, ease-in-out `(0.65, 0, 0.35, 1)` | route cross-fade, sidebar collapse width |
| `spring/rail` | stiffness 320, damping 30 | sidebar 240 → 64, mobile sheet drag |
| `stagger` | 30 ms, max 8 items | first paint of lists and stat tiles only |
| `easing/out-quint` | `cubic-bezier(0.22, 1, 0.36, 1)` | default for anything that enters |

Patterns documented on the Motion page:

- **Sidebar collapse.** Labels fade in the first 120 ms, width animates over
  320 ms, content reflows on the same curve. Tooltips on the rail after 400 ms.
- **Lightbox.** Shared-element zoom from the tile (View Transitions API, FLIP
  fallback), scrim 0 → 98 %, chrome slides in with an 80 ms delay.
- **Loading.** Skeletons mirror the final layout; shimmer 1.4 s; rows enter with
  an 8 px rise, staggered 30 ms, first paint only. Numbers count up over 600 ms.
- **Micro-interactions.** Row/tile hover tint; tile scale 1.02 with overlay;
  tab indicator slides between tabs; hover action cluster rises 4 px; toggle
  knob on a spring; 2 px `accent/glow` focus ring for keyboard focus only.
- **Palette and routes.** ⌘K palette scales 0.98 → 1 with an 8 px backdrop blur;
  results re-rank without layout shift. Sidebar and top bar persist across
  routes; content cross-fades; scroll position is restored per route.
- **Keyboard map.** `⌘K` palette · `⌘1–5` destinations · `⌘\` sidebar · `/`
  search in view · `J/K` next/previous · `G then L` newest · `← →` lightbox ·
  `Esc` close/clear · `?` show map.

---

## 6. Component inventory (Figma page `03 Components`)

Icon set (57) · Button (Primary / Secondary / Ghost / Danger × Md / Sm) ·
IconButton · Chip · NavItem (Default / Hover / Active, swappable icon) · Tab ·
Badge (6 tones) · StatTile · SearchField · TextField · Select · Toggle ·
ProgressBar · Skeleton · Divider · Kbd · Avatar (24/32/40/64) · MessageRow
(Head / Continuation / Hover) · DateDivider · MediaTile (Default / Hover) ·
ChannelRow · CategoryHeader · UserRow · Sidebar · MobileTabBar · CommandPalette ·
EmptyState · Alert (Warning / Danger / Info).

Every fill, stroke, radius, padding and gap in these components is bound to a
variable, so the token file is the source of truth for the implementation.

---

## 7. Implementation plan

Each phase is independently shippable and reviewable.

**Phase 0 — fixes that need no redesign** (small PRs, can land first)

1. Remove the duplicate `{@render children()}` in `+layout.svelte`.
2. Make the reader open at the newest messages and paginate backwards
   (`order=desc` by default, `before=` cursor); fix the button label.
3. Stop the control-page interval when no job is running.
4. Fix the people rank formula; drop the empty-query search on the profile.
5. Return `id` in `stats.top_channels` and link to the channel.
6. Replace the scaffold favicon; derive the version badge from `package.json`.

**Phase 1 — tokens and shell**

- Port the variable collections to `global.css` custom properties; replace the
  three fonts with Instrument Sans + JetBrains Mono.
- Extract primitives: `Button`, `Chip`, `Badge`, `Spinner`→`Skeleton`,
  `EmptyState`, `Alert`, `Kbd`, `Icon` (one SVG sprite, Lucide).
- New `+layout.svelte`: sidebar (with guild switcher reading `/guilds`),
  single scroll container, bottom tab bar under 768 px.

**Phase 2 — Browse**

- `/browse/[channel]` replaces `/channels`, `/timeline` and `/channel/[id]`
  (old routes 301 to the new one).
- `MessageRow` with author grouping (same author within 5 min), sticky
  `DateDivider`, hover actions, reply context from `reference_id`.
- Jump rail backed by a new `GET /channels/{id}/activity?group_by=month`.

**Phase 3 — Media and lightbox**

- `/media` replaces both galleries; `GET /guilds/{id}/gallery/timeline` becomes
  the only gallery endpoint and gains `content_type` and `author_id` filters.
- Justified grid (row height 180, natural aspect from `width`/`height`).
- One `Lightbox` component, View Transitions when available.

**Phase 4 — Search, People, Archive**

- Search chips map to existing API params plus new `before`/`after`/`has`
  filters; expose the `highlight` field the schema already defines.
- `/people` table and profile heatmap (`monthly_activity` → weekly buckets).
- `/archive` with the live-job card; polling only while `busy`.

**API changes implied:** `top_channels[].id`; messages default ordering and a
`before` cursor that returns the newest page first; search `before`/`after`/
`has`; weekly activity for profiles; monthly activity per channel for the jump
rail. All are additive.

---

## 8. Assumptions and open questions

- The archive is single-user and read-only; no auth UI is designed.
- Placeholder art stands in for real attachments and avatars in the Figma file.
- Light theme is out of scope; the token structure (Primitives → Theme) supports
  adding a `Light` mode later without touching components.
- Discord-style "unread" and "typing" affordances are intentionally absent; this
  is an archive, not a client.
