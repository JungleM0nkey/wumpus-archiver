// A profile (#65): breadcrumb, four stat tiles, a 52-week heatmap whose cells are
// labelled with their week and count, top channels, reactions received, and the
// author's newest messages (read with no query), each opening its channel on itself.
// The guard fails a test on any 4xx the page receives.
import type { Locator, Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids and text from tests/smoke_archive.py.
const ALICE_ID = '900000000000000100';
const ART_ID = '900000000000000022';
const ANOTHER_DRAWING_ID = '900000000000001010';
const ALICE_NEWEST_FIRST = [
	'Another drawing',
	'June already?',
	'My first sketch',
	'Agreed.',
	'Anyone up for a game tonight?',
	'Welcome to the smoke test guild!'
];
// Alice's six messages by week (Monday-dated); her last is in the week of Jun 17, 2024.
const ALICE_WEEKS = [
	'Week of May 20, 2024: 3 messages',
	'Week of May 27, 2024: 1 message',
	'Week of Jun 3, 2024: 1 message',
	'Week of Jun 17, 2024: 1 message'
];

const profile = { annotation: { type: ROUTE_ANNOTATION, description: '/people/[id]' } };

function heatmap(page: Page): Locator {
	return page.getByRole('grid', { name: "Alice's messages per week" });
}

function stat(page: Page, label: string): Locator {
	return page.locator('main .stat-card', { hasText: label }).locator('.stat-value');
}

test('a profile has a breadcrumb back to People and four stat tiles', profile, async ({ page }) => {
	await page.goto(`/people/${ALICE_ID}`, { waitUntil: 'networkidle' });
	const crumbs = page.getByRole('navigation', { name: 'Breadcrumb' });
	await expect(crumbs.getByRole('link', { name: 'People' })).toHaveAttribute('href', '/people');
	await expect(crumbs.locator('[aria-current="page"]')).toHaveText('Alice');
	await expect(page.locator('main h1')).toHaveText('Alice');
	await expect(page.locator('main .hero-meta')).toContainText('@alice');

	await expect(page.locator('main .stat-card .stat-label')).toHaveText([
		'Messages',
		'Attachments',
		'Reactions received',
		'Active channels'
	]);
	await expect(stat(page, 'Messages')).toHaveText('6');
	await expect(stat(page, 'Attachments')).toHaveText('2');
	await expect(stat(page, 'Reactions received')).toHaveText('6');
	await expect(stat(page, 'Active channels')).toHaveText('3');
});

test('the heatmap has a labelled cell for each of 52 weeks, summing to the messages in them', profile, async ({
	page
}) => {
	await page.goto(`/people/${ALICE_ID}`, { waitUntil: 'networkidle' });
	const cells = heatmap(page).getByRole('gridcell');
	await expect(cells).toHaveCount(52);
	const labels = await cells.evaluateAll((els) => els.map((el) => el.getAttribute('aria-label') ?? ''));
	const pattern = /^Week of ([A-Z][a-z]{2} \d{1,2}, \d{4}): (\d+) messages?$/;
	expect(labels.every((label) => pattern.test(label)), labels.join('\n')).toBe(true);

	// Consecutive Mondays, the last the week of Alice's last message.
	const mondays = labels.map((label) => new Date(`${label.match(pattern)![1]} UTC`));
	expect(mondays.every((d) => d.getUTCDay() === 1)).toBe(true);
	expect(mondays.slice(1).every((d, i) => d.getTime() - mondays[i].getTime() === 7 * 864e5)).toBe(true);
	expect(labels.at(-1)).toBe('Week of Jun 17, 2024: 1 message');

	// All six of her messages fall in the window, so the weeks sum to her Messages tile.
	const counts = labels.map((label) => Number(label.match(pattern)![2]));
	expect(counts.reduce((a, b) => a + b, 0)).toBe(Number(await stat(page, 'Messages').innerText()));
	expect(labels.filter((label) => !label.endsWith(': 0 messages'))).toEqual(ALICE_WEEKS);
	await expect(page.locator('main .heatmap .detail')).toHaveText(
		'6 messages in the 52 weeks to Jun 23, 2024; busiest the week of May 20, 2024, 3'
	);
});

test('the heatmap is one tab stop the arrow keys move through, reading out each week', profile, async ({
	page
}) => {
	await page.goto(`/people/${ALICE_ID}`, { waitUntil: 'networkidle' });
	const cells = heatmap(page).getByRole('gridcell');
	await expect(cells.and(page.locator('[tabindex="0"]'))).toHaveCount(1);
	await cells.last().focus();
	await expect(page.locator('main .heatmap .detail')).toHaveText(ALICE_WEEKS[3]);
	await page.keyboard.press('Home');
	await expect(cells.first()).toBeFocused();
	await page.keyboard.press('End');
	await page.keyboard.press('ArrowLeft');
	await expect(cells.nth(50)).toBeFocused();
	await expect(cells.nth(50)).toHaveAttribute('tabindex', '0');
	await expect(page.locator('main .heatmap .detail')).toHaveText('Week of Jun 10, 2024: 0 messages');
});

test('top channels and reactions received link and count', profile, async ({ page }) => {
	await page.goto(`/people/${ALICE_ID}`, { waitUntil: 'networkidle' });
	const channels = page.locator('main section', { has: page.getByRole('heading', { name: 'Top channels' }) });
	await expect(channels.getByRole('link')).toHaveCount(3);
	await expect(channels.getByRole('link', { name: /#art/ })).toHaveAttribute('href', `/channel/${ART_ID}`);

	const reactions = page.locator('main section', { has: page.getByRole('heading', { name: 'Reactions received' }) });
	await expect(reactions.locator('.section-sub')).toHaveText('6 reactions on their messages');
	await expect(reactions.getByRole('listitem')).toHaveCount(4);
	await expect(reactions.getByRole('listitem', { name: '👋: 2 reactions' })).toBeVisible();
});

test("a profile's recent messages are the author's newest, each opening its channel on it", profile, async ({
	page
}) => {
	const read = page.waitForRequest((request) => new URL(request.url()).pathname === '/api/search');
	await page.goto(`/people/${ALICE_ID}`, { waitUntil: 'networkidle' });
	const params = new URL((await read).url()).searchParams;
	expect(params.get('author_id')).toBe(ALICE_ID);
	expect(params.has('q')).toBe(false);

	const recent = page.locator('main .recent');
	await expect(recent.locator('.recent-content')).toHaveText(ALICE_NEWEST_FIRST);
	const first = recent.getByRole('link').first();
	await expect(first).toHaveAttribute('href', `/channel/${ART_ID}?message=${ANOTHER_DRAWING_ID}`);
	await first.click();
	await expect(page).toHaveURL(`/channel/${ART_ID}?message=${ANOTHER_DRAWING_ID}`);
	await expect(page.locator('main').getByText('Another drawing')).toBeVisible();
});
