// The scrape status the shell's archive card and the Archive screen share. It is read
// once when the portal opens, and the archive card polls it every POLL_MS while a
// scrape job runs, so no screen reads /api/scrape/status on its own: a screen awaits
// `scrapeStatus.load()` and reads `scrapeStatus.status`, and calls `refresh()` after
// it starts or cancels a job.
import { getScrapeStatus } from './api';
import type { ScrapeStatusResponse } from './types';

/** How often a running scrape job's status is read. */
export const POLL_MS = 2_000;

let status = $state<ScrapeStatusResponse | null>(null);
let error = $state('');
let first: Promise<void> | null = null;

export const scrapeStatus = {
	/** The last status read, or null until the first read succeeds. */
	get status(): ScrapeStatusResponse | null {
		return status;
	},
	/** Why the last read failed, or ''. */
	get error(): string {
		return error;
	},
	/** Whether a scrape job is running. */
	get busy(): boolean {
		return status?.busy ?? false;
	},
	/** The first read: started by the first call, shared by every later one. */
	load(): Promise<void> {
		first ??= scrapeStatus.refresh().then(() => undefined);
		return first;
	},
	/** Read the status again; resolves to it, or null when the read failed. */
	async refresh(): Promise<ScrapeStatusResponse | null> {
		try {
			status = await getScrapeStatus();
			error = '';
			return status;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to read the scrape status';
			return null;
		}
	}
};
