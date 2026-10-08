// The Archive screen (/archive, #66): /control redirects to it; without a bot token
// its form is disabled and an alert says why; a scrape job started from it shows
// live, cancels after a confirmation and then shows in the history. It polls scrape
// status only while a scrape job runs, and re-reads history only when that job
// finishes. The page's clock is paused, so time moves only when a test runs it forward.
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
	await page.goto('/archive', { waitUntil: 'networkidle' });
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
					guild_id: '1',
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

	await page.goto('/archive', { waitUntil: 'networkidle' });
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

// Ids from tests/smoke_archive.py.
const GUILD_ID = '900000000000000001';
const NIGHT_ID = '900000000000000002';

test('/control redirects to /archive, keeping the selected guild', async ({ page }) => {
	await page.goto('/control', { waitUntil: 'networkidle' });
	await expect(page).toHaveURL('/archive');
	await expect(page.locator('main h1')).toHaveText('Archive');

	await page.goto(`/control?guild=${NIGHT_ID}`, { waitUntil: 'networkidle' });
	await expect(page).toHaveURL(`/archive?guild=${NIGHT_ID}`);
	await expect(page.locator('#guild-select')).toHaveValue(NIGHT_ID);
});

test('without a bot token the form is disabled and an alert says why and how to enable it', async ({
	page
}) => {
	// The smoke server runs with blank tokens, so scrape control is read-only.
	await page.goto('/archive', { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await expect(main.getByText('Scrape control is read-only')).toBeVisible();
	await expect(main.getByText(/No bot token was configured/)).toBeVisible();
	await expect(main.locator('code', { hasText: 'DISCORD_BOT_TOKEN' })).toBeVisible();

	await expect(page.getByLabel('Guild', { exact: true })).toBeDisabled();
	await expect(page.getByLabel('API token')).toBeDisabled();
	await expect(page.getByRole('button', { name: 'Start scrape' })).toBeDisabled();
	await expect(main.getByText('Needs a bot token on the server.')).toBeVisible();
	await expect(main.getByText('No scrape job running.')).toBeVisible();
});

const API_TOKEN = 'smoke-api-token-not-a-secret';

interface FakeChannel {
	id: string;
	name: string;
	messages: number;
	done: boolean;
}

interface FakeJob {
	id: string;
	guild_id: string;
	status: string;
	progress: {
		current_channel: string;
		channels_done: number;
		messages_scraped: number;
		attachments_found: number;
		errors: string[];
		channels: FakeChannel[];
	};
	started_at: string;
	completed_at: string | null;
	result: null;
	error_message: null;
	duration_seconds: number;
}

/**
 * Scrape control as a server with both tokens answers it, in the page's routes: a
 * started job reports #general, then #art as #general finishes, one step per status
 * read; cancel ends it and puts it in the history.
 */
async function fakeScrapeControl(page: Page) {
	const server = {
		job: null as FakeJob | null,
		history: [] as FakeJob[],
		reads: 0,
		authorization: [] as (string | null)[]
	};
	const busy = () => server.job?.status === 'scraping';
	const steps: FakeChannel[][] = [
		[{ id: '1', name: 'general', messages: 100, done: false }],
		[
			{ id: '1', name: 'general', messages: 140, done: true },
			{ id: '2', name: 'art', messages: 7, done: false }
		]
	];

	await page.route('**/api/scrape/status', async (route) => {
		const job = server.job;
		if (job && busy()) {
			const channels = steps[Math.min(server.reads, steps.length - 1)];
			server.reads += 1;
			job.progress = {
				...job.progress,
				channels,
				current_channel: channels[channels.length - 1].name,
				channels_done: channels.filter((c) => c.done).length,
				messages_scraped: channels.reduce((n, c) => n + c.messages, 0)
			};
			job.duration_seconds += 2;
		}
		await route.fulfill({
			json: { busy: busy(), current_job: job, has_token: true, control_enabled: true }
		});
	});
	await page.route('**/api/scrape/start', async (route) => {
		server.authorization.push(await route.request().headerValue('authorization'));
		const body = route.request().postDataJSON();
		server.job = {
			id: 'smoke-job-1',
			guild_id: body.guild_id,
			status: 'scraping',
			progress: {
				current_channel: '',
				channels_done: 0,
				messages_scraped: 0,
				attachments_found: 0,
				errors: [],
				channels: []
			},
			started_at: T0.toISOString(),
			completed_at: null,
			result: null,
			error_message: null,
			duration_seconds: 0
		};
		await route.fulfill({ status: 202, json: { job: server.job } });
	});
	await page.route('**/api/scrape/cancel', async (route) => {
		server.authorization.push(await route.request().headerValue('authorization'));
		const job = server.job!;
		job.status = 'cancelled';
		job.completed_at = T0.toISOString();
		server.history.unshift(structuredClone(job));
		await route.fulfill({ json: { message: 'Cancellation requested' } });
	});
	await page.route('**/api/scrape/history', (route) => route.fulfill({ json: { jobs: server.history } }));
	return server;
}

test('a started scrape job shows live, cancels after a confirmation, then shows in the history', async ({
	page
}) => {
	const server = await fakeScrapeControl(page);
	const calls = scrapeCalls(page);
	await page.goto('/archive', { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await expect(main.getByText('Scrape control is read-only')).toHaveCount(0);
	await expect(page.locator('#guild-select')).toHaveValue(GUILD_ID);

	// Start a scrape of the selected guild, with the API token.
	await page.getByLabel('API token').fill(API_TOKEN);
	await page.getByRole('button', { name: 'Start scrape' }).click();

	const card = main.locator('section[aria-labelledby="job-card-title"]');
	await expect(card.getByText('scraping').first()).toBeVisible();
	await expect(card.getByText('Smoke Test Guild')).toBeVisible();
	await expect(card.getByText('#general').first()).toBeVisible();
	await expect(card.getByRole('progressbar', { name: 'Scraping' })).toBeVisible();
	expect(server.authorization).toEqual([`Bearer ${API_TOKEN}`]);

	// The next poll: #general is done, #art is being scraped, and the counters follow.
	await runFor(page, POLL_MS);
	const rows = card.getByRole('list', { name: 'Channel status' }).getByRole('listitem');
	await expect(rows).toHaveCount(2);
	await expect(rows.nth(0)).toHaveAttribute('data-state', 'scraping');
	await expect(rows.nth(0)).toContainText('#art');
	await expect(rows.nth(1)).toHaveAttribute('data-state', 'done');
	await expect(rows.nth(1)).toContainText('140');
	await expect(card.getByText('1 of 2 done')).toBeVisible();
	await expect(card.locator('.counter', { hasText: 'Messages' })).toContainText('147');

	// Cancel asks first; keeping it running changes nothing.
	await card.getByRole('button', { name: 'Cancel scrape job' }).click();
	await expect(card.getByText('Cancel this scrape job?')).toBeVisible();
	await expect(card.getByRole('button', { name: 'Cancel job' })).toBeFocused();
	await card.getByRole('button', { name: 'Keep running' }).click();
	await expect(card.getByText('Cancel this scrape job?')).toHaveCount(0);
	expect(server.authorization).toHaveLength(1);

	await card.getByRole('button', { name: 'Cancel scrape job' }).click();
	await card.getByRole('button', { name: 'Cancel job' }).click();
	await expect(card.getByText('cancelled').first()).toBeVisible();
	await expect(card.getByRole('button', { name: /Cancel/ })).toHaveCount(0);
	await expect(rows.nth(0)).toHaveAttribute('data-state', 'stopped');
	expect(server.authorization).toEqual([`Bearer ${API_TOKEN}`, `Bearer ${API_TOKEN}`]);

	// The history, read again now that the job ended, lists it.
	const history = main.locator('section[aria-labelledby="history-title"]');
	const row = history.getByRole('row', { name: /smoke-job-1/ });
	await expect(row).toBeVisible();
	await expect(row).toContainText('cancelled');
	await expect(row).toContainText('Smoke Test Guild');
	await expect(row).toContainText('147');

	// Idle again: nothing is polled, and the token stayed in this tab's sessionStorage only.
	const settled = { ...calls };
	await runFor(page, 60_000);
	expect(calls).toEqual(settled);
	const stored = await page.evaluate(() => ({
		local: JSON.stringify({ ...localStorage }),
		session: JSON.stringify({ ...sessionStorage })
	}));
	expect(stored.local).not.toContain(API_TOKEN);
	expect(stored.session).toContain(API_TOKEN);
});

test('a scrape job names its guild by exact id, above 2^53 and not in the archive', async ({
	page
}) => {
	// #68: guild ids are matched as strings. This one is not in the archive, and a
	// JavaScript number would round it (to ...064). Night Owls' id rounds to the same
	// number as Smoke Test Guild's, so only an exact match names it.
	const OUTSIDE_ID = '165682173540696065';
	const job = (id: string, guild_id: string) => ({
		id,
		guild_id,
		status: 'completed',
		progress: {
			current_channel: '',
			channels_done: 3,
			messages_scraped: 21,
			attachments_found: 0,
			errors: [],
			channels: []
		},
		started_at: T0.toISOString(),
		completed_at: T0.toISOString(),
		result: null,
		error_message: null,
		duration_seconds: 4
	});
	const outside = job('smoke-job-outside', OUTSIDE_ID);
	await page.route('**/api/scrape/status', (route) =>
		route.fulfill({
			json: { busy: false, current_job: outside, has_token: true, control_enabled: true }
		})
	);
	await page.route('**/api/scrape/history', (route) =>
		route.fulfill({ json: { jobs: [outside, job('smoke-job-night', NIGHT_ID)] } })
	);

	await page.goto('/archive', { waitUntil: 'networkidle' });
	const main = page.locator('main');
	const card = main.locator('section[aria-labelledby="job-card-title"]');
	await expect(card.locator('.guild-name')).toHaveText(`Guild ${OUTSIDE_ID}`);
	const history = main.locator('section[aria-labelledby="history-title"]');
	const guildOf = (jobId: string) =>
		history.getByRole('row', { name: new RegExp(jobId) }).locator('td.guild');
	await expect(guildOf('smoke-job-outside')).toHaveText(`Guild ${OUTSIDE_ID}`);
	await expect(guildOf('smoke-job-night')).toHaveText('Night Owls');
});
