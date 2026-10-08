// The Overview (#67): the selected guild's totals with their change since the last
// completed scrape job, messages per month, the most active channels and top
// contributors, and the archive's health.
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures.ts';

// Ids and text from tests/smoke_archive.py. Night Owls alone has a completed scrape job
// on record, which added three messages and an attachment.
const GUILD_ID = '900000000000000001';
const NIGHT_ID = '900000000000000002';
const GENERAL_ID = '900000000000000020';
const ALICE_ID = '900000000000000100';

function tile(page: Page, label: string) {
	return page.locator('main .stat-card', { hasText: label });
}

/** Every calendar month from the first bucket's to the last's, as YYYY-MM. */
function monthsSpanned(starts: string[]): string[] {
	const [y0, m0] = starts[0].split('-').map(Number);
	const [y1, m1] = starts[starts.length - 1].split('-').map(Number);
	const months: string[] = [];
	for (let y = y0, m = m0; y < y1 || (y === y1 && m <= m1); m === 12 ? ((y += 1), (m = 1)) : (m += 1)) {
		months.push(`${y}-${String(m).padStart(2, '0')}`);
	}
	return months;
}

test('an Overview top channel opens that channel', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.getByRole('link', { name: '#general' }).click();

	await expect(page).toHaveURL(`/browse/${GENERAL_ID}`);
	await expect(page.locator('main').getByText('Anyone up for a game tonight?').first()).toBeVisible();
});

test('a top contributor opens their profile', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.locator('main').getByRole('link', { name: /Alice/ }).click();
	await expect(page).toHaveURL(new RegExp(ALICE_ID));
});

test('the most active channels are text channels, without the categories', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const section = page.getByRole('region', { name: 'Most Active Channels' });
	const names = await section.locator('.bar-label').allInnerTexts();
	expect(names).toEqual(['#lobby', '#general', '#random', '#art']);
	await expect(section.getByText('Text Channels')).toHaveCount(0);
	await expect(section.getByText('Media', { exact: true })).toHaveCount(0);
});

test("the tiles read Messages, Channels, Authors and Attachments, with the guild's totals", async ({
	page
}) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const labels = await page.locator('main .stat-card .stat-label').allInnerTexts();
	expect(labels.map((l) => l.toLowerCase())).toEqual(['messages', 'channels', 'authors', 'attachments']);
	await expect(tile(page, 'Messages').locator('.stat-value')).toHaveText('135');
	await expect(tile(page, 'Authors').locator('.stat-value')).toHaveText('122');
});

test('with no completed scrape job the tiles show no change, not zero', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await expect(page.locator('main .stat-card')).toHaveCount(4);
	await expect(page.locator('main .stat-change')).toHaveCount(0);
	await expect(page.locator('main')).not.toContainText('since last scrape');
});

test("after a completed scrape job each tile shows its change since then", async ({ page }) => {
	await page.goto(`/?guild=${NIGHT_ID}`, { waitUntil: 'networkidle' });
	await expect(tile(page, 'Messages').locator('.stat-change')).toHaveText('+3 since last scrape');
	await expect(tile(page, 'Channels').locator('.stat-change')).toHaveText('No change since last scrape');
	await expect(tile(page, 'Authors').locator('.stat-change')).toHaveText('No change since last scrape');
	await expect(tile(page, 'Attachments').locator('.stat-change')).toHaveText('+1 since last scrape');
	await expect(page.locator('.health .scrape')).toContainText('Completed');
});

test("the chart has one point per month of the guild's activity", async ({ page, request }) => {
	for (const id of [GUILD_ID, NIGHT_ID]) {
		const activity = await (await request.get(`/api/guilds/${id}/activity`)).json();
		const expected = monthsSpanned(activity.buckets.map((b: { start: string }) => b.start));

		await page.goto(`/?guild=${id}`, { waitUntil: 'networkidle' });
		const points = page.locator('main .chart-point');
		await expect(points).toHaveCount(expected.length);
		expect(await points.evaluateAll((els) => els.map((el) => el.getAttribute('data-month')))).toEqual(expected);

		// The table lists the same months, with the API's counts.
		await page.getByText('Show as a table').click();
		const rows = page.locator('main .chart-table tbody tr');
		await expect(rows).toHaveCount(expected.length);
		const counts = (await rows.locator('td').allInnerTexts()).map(Number);
		expect(counts.reduce((a, b) => a + b, 0)).toBe(
			activity.buckets.reduce((sum: number, b: { messages: number }) => sum + b.messages, 0)
		);
	}
});

test('the chart has axis labels, a summary, and reads each month by hover or keyboard', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const chart = page.locator('main .activity-chart');
	await expect(chart.locator('figcaption')).toContainText('135 messages over 2 months, May 2024 to Jun 2024.');
	await expect(chart.locator('.y-tick').first()).toHaveText('0');
	await expect(chart.locator('.x-tick')).toHaveText(['May 2024', 'Jun']);

	const plot = chart.getByRole('slider', { name: /Messages per month/ });
	const box = (await plot.locator('svg').boundingBox())!;
	await page.mouse.move(box.x + 60, box.y + box.height / 2);
	await expect(chart.locator('.chart-tooltip')).toContainText('May 2024');
	await expect(chart.locator('.chart-tooltip')).toContainText('8 messages');

	await page.mouse.move(0, 0);
	await plot.focus();
	await expect(plot).toHaveAttribute('aria-valuetext', 'Jun 2024: 127 messages');
	await page.keyboard.press('ArrowLeft');
	await expect(plot).toHaveAttribute('aria-valuetext', 'May 2024: 8 messages');
	await expect(chart.locator('.chart-tooltip')).toContainText('May 2024');
});

test("the archive health card's attachment progress matches download stats", async ({ page, request }) => {
	const stats = await (await request.get('/api/downloads/stats')).json();
	expect(stats.total_images).toBeGreaterThan(0);

	await page.goto('/', { waitUntil: 'networkidle' });
	const card = page.locator('main .health');
	await expect(card.locator('.downloaded-count')).toHaveText(`${stats.downloaded} of ${stats.total_images}`);
	const meter = card.getByRole('progressbar', { name: 'Images downloaded' });
	await expect(meter).toHaveAttribute(
		'aria-valuenow',
		String(Math.round((stats.downloaded / stats.total_images) * 100))
	);
	await expect(card.locator('.health-value')).toHaveText(
		`${Math.floor((stats.downloaded / stats.total_images) * 100)}%`
	);
	// The smoke server runs without a bot token.
	await expect(card.locator('.token')).toContainText('Not configured');
	await expect(card.locator('.scrape')).toContainText('Scraped');
});

test('the archive health card leads to the Archive screen', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const link = page.locator('main .health').getByRole('link', { name: 'Open the Archive screen' });
	const href = await page.locator('.sidebar .status-card').getAttribute('href');
	await link.click();
	await expect(page).toHaveURL(href!);
});

/** Every text the first tile's value shows from the moment the page starts. */
async function recordFirstValue(page: Page): Promise<void> {
	await page.addInitScript(() => {
		const seen: string[] = [];
		(window as unknown as { seenValues: string[] }).seenValues = seen;
		new MutationObserver(() => {
			const value = document.querySelector('main .stat-card .stat-value')?.textContent?.trim();
			if (value && seen[seen.length - 1] !== value) seen.push(value);
		}).observe(document, { subtree: true, childList: true, characterData: true });
	});
}

test('the totals count up when they first paint', async ({ page }) => {
	await recordFirstValue(page);
	await page.goto('/', { waitUntil: 'networkidle' });
	await expect(tile(page, 'Messages').locator('.stat-value')).toHaveText('135');
	const seen = await page.evaluate(() => (window as unknown as { seenValues: string[] }).seenValues);
	expect(seen[0]).toBe('0');
	expect(seen.length).toBeGreaterThan(2);
	expect(seen[seen.length - 1]).toBe('135');
});

test('under reduced motion the totals show at once', async ({ page }) => {
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await recordFirstValue(page);
	await page.goto('/', { waitUntil: 'networkidle' });
	await expect(tile(page, 'Messages').locator('.stat-value')).toHaveText('135');
	const seen = await page.evaluate(() => (window as unknown as { seenValues: string[] }).seenValues);
	expect(seen).toEqual(['135']);
});
