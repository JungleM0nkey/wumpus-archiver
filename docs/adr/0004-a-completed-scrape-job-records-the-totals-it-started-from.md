# A completed scrape job records the totals it started from

The Overview shows each guild total (messages, channels, authors, attachments) with its change since the last scrape. The archive kept nothing that could say what that change was: scrape job history lives in the scrape job manager's memory, so it is lost on restart and never includes a scrape run from the CLI; `Guild.last_scraped_at` is overwritten by each scrape; `Message.scraped_at` is the first-ingest time of messages only, and channels and authors have no ingest time at all.

So each scrape job that completes now leaves one row in a new `completed_scrapes` table: the guild, when the job started and completed, and the guild's totals when it started, read by `archive_reads.guild_totals` before the job writes anything. `ArchiverBot.scrape_guild` writes it, so the portal's jobs and the CLI's are both recorded. The stats route reads the same `guild_totals` and reports `since_last_scrape` as today's totals minus the latest row's: what the last completed job added, plus anything ingested since. With no row, `since_last_scrape` is `null`, never zeros, and the portal shows no change.

## Considered options

- **Rows ingested since the last job, from ingest timestamps.** Rejected: only messages carry one, so channels and authors could not be counted, and the only reliable job time (`Guild.last_scraped_at`) is when the last job ended, which leaves nothing to count.
- **Totals recorded when a job ends, compared with today's.** Rejected: only a scrape writes to the archive, so the change would be zero right after every scrape and stay there, which says nothing.
- **Keep it in the in-memory job history.** Rejected: it is empty after every restart and never sees a CLI scrape.
- **Columns on `guilds`.** Rejected: `create_all` does not add columns to an existing table, so every archive would need a migration; a new table needs none.

## Consequences

- The change is additive. `serve` does not create tables, so an archive from before this change has no `completed_scrapes` until its next scrape, which runs `create_tables` first. Until then `last_completed_scrape` reads the missing table as no completed job.
- A failed or cancelled job leaves no row, so the change is always measured from a job that completed.
- The stats route now counts a guild's channels with `count(*)` rather than loading them, and pays one more statement for the latest row.
