# Wumpus Archiver

A tool that copies a Discord server into a local archive and lets people explore that copy through a web portal.

## Language

### The archive

**Archive**:
The stored copy of one or more guilds: their channels, messages, users, reactions and attachments.
_Avoid_: database (the storage, not the thing stored), export, dump

**Guild**:
A Discord server as Discord names it. The unit the archiver scrapes and the portal browses.
_Avoid_: server

**Attachment**:
A file posted with a message. The archive always records it; a copy of the file itself is only present once it has been downloaded.

**Local attachment**:
An attachment whose file has been downloaded into the attachments dir, so the portal can serve it instead of linking to Discord.
_Avoid_: downloaded image, cached attachment

**Attachments dir**:
The directory on disk where local attachments live and that the portal serves them from.
_Avoid_: attachments path, attachments folder

### Scraping

**Scrape**:
Reading a guild from Discord and writing it into the archive. Re-scraping a guild updates its archive rather than duplicating it.
_Avoid_: export, sync, import, crawl

**Scrape job**:
One run of a scrape against one guild, with a status (pending, connecting, scraping, completed, failed, cancelled) and progress.
_Avoid_: task, run, crawl

**Change since the last scrape**:
How much a guild total differs from what it was when the guild's last completed scrape job started: what that job added, plus anything ingested since. A guild with no completed scrape job on record has none, which is not the same as zero.
_Avoid_: delta (in copy), growth

**Scrape control**:
The ability to start and cancel scrape jobs from the portal. It is read-only when no bot token is configured.
_Avoid_: control panel, control page, scrape manager (the implementation)

**Bot token**:
The Discord credential a scrape runs under.
_Avoid_: discord token, token (on its own, in prose)

### Reading the archive

**Archive reads**:
The named reads of the archive that the portal's routes and the downloader call, each over a scope.
_Avoid_: queries, repositories (the write side), the read layer

**Scope**:
Which part of the archive a read covers: an optional guild, channel and author, all applied together. An empty scope is the whole archive.
_Avoid_: filter, selection

**Cursor**:
A message id used to page through messages. "Before" means the page adjacent to it on the older side, "after" the page adjacent on the newer side, and "around" the page that holds the message itself with its neighbours on both sides.
_Avoid_: offset (a different paging style), position

**Total**:
The exact count of everything a read matches, ignoring paging. Never the length of the returned list.
_Avoid_: count (ambiguous), size

**Activity**:
Message counts per calendar month or week over a whole scope.
_Avoid_: monthly_activity (a field), timeline groups (page-local)

**Authors**:
The users who have posted at least one message in a scope, with their counts.
_Avoid_: people (the screen), members

**Search terms**:
The words of a search query, each of which a matching message must contain, in any order and case; a double-quoted phrase is one term. Filter chips (`in:`, `from:`, `has:`, `after:`, `before:`) are not terms.
_Avoid_: keywords, query (the whole text, chips included)

**Facets**:
How a search's matches divide by channel, by author and by month, counted for the same terms and filters.
_Avoid_: aggregations, buckets (an activity read's)

**Gallery timeline**:
The grouped-attachments endpoint behind the Media screen.
_Avoid_: timeline (the old chronological message page)

### The portal

**Portal**:
The web interface for exploring the archive.
_Avoid_: frontend, UI, dashboard, site

**Portal dir**:
The portal's source project directory.
_Avoid_: portal folder, frontend dir

**Portal build**:
The portal's built static output, which the archiver serves alongside its API.
_Avoid_: dist, portal dist, static files

**Archive screen**:
The portal page where people watch and operate scrape control. Named for what it manages, not for the data.
_Avoid_: control page, scrape page

**Media screen**:
The portal page that shows attachments across a guild, fed by the gallery timeline.
_Avoid_: gallery (the endpoint family), images page

**Lightbox**:
The dialog that shows one attachment large, over the Media screen or Browse's Media tab, with a filmstrip of the others loaded beside it.
_Avoid_: viewer, modal, image popup

**People screen**:
The portal page that lists authors.
_Avoid_: users page, members page

**Jump rail**:
Browse's column of a channel's years and months, each with its message count from the channel's activity. Picking a month opens the reader at that month's first message.
_Avoid_: timeline, date picker
