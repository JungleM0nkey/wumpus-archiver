# Archive reads take the caller's session and return their own totals

The archive's read side is one module of named reads (`messages`, `attachments`, `authors`, `guild_channels`, `guild_counts`, `top_channels`, `activity`, `summary`, `reactions`) over a `Scope` (guild, channel, author, all optional, all applied together). Every read takes the `AsyncSession` its caller opened, exactly as the write-side repositories do, and never commits, flushes or closes it. Every paged read returns a `Page` whose `total` is computed from the same predicate list as its rows, so a results/count divergence (the search bug this replaces) cannot be written in a handler.

## Considered options

- **Reads take a `Database` and open a session per call.** Rejected: a profile or stats request would pay four to six sessions, and the module would own a lifecycle the routes already own.
- **A per-request reader object injected into routes.** Deferred: it can be added later as a dependency that opens one session and hands it to these same functions, without changing them.
- **A separate `count()` call beside the page.** Rejected: agreement between rows and total becomes route discipline, which is how the divergence happened.

## Consequences

- `has_more` comes from fetching one row past the limit, never from the count. The COUNT is skipped when the first page is already the whole result; otherwise it runs, so a message page nobody reads the total of still pays one `count(*)`. All counts are `count(*)`, never `count(<primary key>)`, which on SQLite leaves the covering index.
- On SQLite a shared session is a shared connection, not a snapshot: a total is the count at the moment of its statement.
- A channel outside the requested guild yields an empty page rather than today's silent "channel wins"; there is no live caller for the mismatched case.
- The module emits only SQLAlchemy constructs that compile on both the sqlite and postgresql dialects (activity is bucketed with `extract` and folded in Python; no `strftime`, `random()` or `text()`), but promises SQLite behaviour only, because no other adapter exists to test against.
- `top_channels` keeps reading the ingest-maintained `Channel.message_count` and says so; whether that counter survives is a separate decision, and this module should not pre-empt it.
