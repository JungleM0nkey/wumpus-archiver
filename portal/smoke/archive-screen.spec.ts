// The Archive screen polls scrape status only while a scrape job runs, and re-reads
// history only when that job finishes. The page's clock is paused, so time moves
// only when a test runs it forward.
import type { Page, Request } from '@playwright/test';
import { expect, test } from './fixtures.ts';

const POLL_MS = 2_000;
const T0 = new Date('2026-01-01T00:00:00Z');

function scrapeCalls(page: Page): { status: number; history: number } {
	const calls = { status: 0, history: 0 };
	page.on('request', (request: Request) => {
		const path = new URL(request.url()).pathname;
		if (path === '/api/scrape/status') calls.status += 1;
		if (path === '/api/scrape/history') calls.history += 1;
	});
	return calls;
}

/** Run the page's clock forward, then give any request a timer started time to show. */
async function runFor(page: Page, ms: number): Promise<void> {
	await page.clock.runFor(ms);
	await page.waitForTimeout(300);
}

test.beforeEach(async ({ page }) => {
	await page.clock.install({ time: T0 });
	await page.clock.pauseAt(new Date(T0.getTime() + 1_000));
});

test('with no scrape job running, the Archive screen makes no status requests after loading', async ({
	page
}) => {
	const calls = scrapeCalls(page);
	await page.goto('/control', { waitUntil: 'networkidle' });
	await expect(page.locator('main').getByText('.smoke-archive/attachments').first()).toBeVisible();
	expect(calls).toEqual({ status: 1, history: 1 });

	await runFor(page, 60_000);
	expect(calls).toEqual({ status: 1, history: 1 });
});

test('a running scrape job is polled until it finishes, then history is read once', async ({
	page
}) => {
	// The smoke server is read-only and never runs a job, so its status answers are
	// rewritten: the first two say a job is scraping, every later one that it completed.
	let answered = 0;
	await page.route('**/api/scrape/status', async (route) => {
		const real = await (await route.fetch()).json();
		answered += 1;
		const running = answered <= 2;
		await route.fulfill({
			json: {
				...real,
				busy: running,
				current_job: {
					id: 'smoke-job',
					guild_id: 1,
					status: running ? 'scraping' : 'completed',
					progress: {
						current_channel: 'general',
						channels_done: 1,
						messages_scraped: 12,
						attachments_found: 4,
						errors: []
					},
					started_at: T0.toISOString(),
					completed_at: running ? null : T0.toISOString(),
					result: null,
					error_message: null,
					duration_seconds: 4
				}
			}
		});
	});
	const calls = scrapeCalls(page);

	await page.goto('/control', { waitUntil: 'networkidle' });
	await expect(page.locator('main').getByText('scraping').first()).toBeVisible();
	expect(calls).toEqual({ status: 1, history: 1 });

	// Still running: the status is polled, history is not re-read.
	await runFor(page, POLL_MS);
	expect(calls).toEqual({ status: 2, history: 1 });

	// The job finishes: history is read once more.
	await runFor(page, POLL_MS);
	await expect(page.locator('main').getByText('completed').first()).toBeVisible();
	expect(calls).toEqual({ status: 3, history: 2 });

	// Idle again: polling has stopped.
	await runFor(page, 60_000);
	expect(calls).toEqual({ status: 3, history: 2 });
});
