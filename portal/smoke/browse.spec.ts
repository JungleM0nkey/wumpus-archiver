// Browse (#60): one reader at /browse/<channel> beside a channel pane grouped by
// category. The old channel routes redirect to it with the same channel selected, and a
// message link (`?message=<id>`) opens the feed on that message, with older and newer
// pages loadable around it.
import type { Locator, Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';
import { narrowPages, topOf } from './reader.ts';

// Ids and text from tests/smoke_archive.py.
const GENERAL_ID = '900000000000000020';
const LOBBY_ID = '900000000000000023';
const NIGHT_ID = '900000000000000002';
const LOUNGE_ID = '900000000000000031';
/** "Anyone up for a game tonight?", general's third message. */
const GAME_ID = '900000000000001002';
/** "The hello world of June.", general's newest. */
const HELLO_ID = '900000000000001009';

/** The message id of lurker `n`'s one message in #lobby, posted in the order of `n`. */
const lurkerMessage = (n: number) => String(900000000000003000n + BigInt(n - 1));
const lurkerText = (n: number) => `Lurker ${String(n).padStart(3, '0')} says hi.`;
/** #lobby's newest message, after the lurkers'. */
const LOBBY_NEWEST = 'aaron checks in, 2 of 2.';

const annotation = { type: ROUTE_ANNOTATION, description: '/browse/[channel]' };

function pane(page: Page): Locator {
	return page.getByRole('complementary', { name: 'Channels' });
}

/** The channel pane's rows as "name count" lines. */
async function paneRows(page: Page): Promise<string[]> {
	const rows = await pane(page).locator('.channel-item').allInnerTexts();
	return rows.map((row) => row.replace(/\s+/g, ' ').trim());
}

/** The message card of message `id`. */
function card(page: Page, id: string): Locator {
	return page.locator(`main [data-message-id="${id}"]`);
}

// ── The old routes ──────────────────────────────────────────────────────────

for (const [from, to, heading] of [
	[`/channel/${GENERAL_ID}`, `/browse/${GENERAL_ID}`, 'general'],
	[`/timeline?channel=${GENERAL_ID}`, `/browse/${GENERAL_ID}`, 'general'],
	[`/channel/${LOUNGE_ID}?guild=${NIGHT_ID}`, `/browse/${LOUNGE_ID}?guild=${NIGHT_ID}`, 'lounge'],
	[`/channel/${GENERAL_ID}?message=${GAME_ID}`, `/browse/${GENERAL_ID}?message=${GAME_ID}`, 'general'],
	// No channel named: Browse opens the guild's most active channel.
	['/channels', `/browse/${LOBBY_ID}`, 'lobby'],
	['/timeline', `/browse/${LOBBY_ID}`, 'lobby'],
	[`/channels?guild=${NIGHT_ID}`, `/browse/${LOUNGE_ID}?guild=${NIGHT_ID}`, 'lounge']
]) {
	test(`${from} redirects to ${to}`, { annotation }, async ({ page }) => {
		await page.goto(from, { waitUntil: 'networkidle' });
		await expect(page).toHaveURL(to);
		const main = page.locator('main');
		await expect(main.getByRole('heading', { level: 1 })).toHaveText(heading);
		await expect(pane(page).locator('[aria-current="page"]')).toContainText(heading);
	});
}

test('/browse replaces itself with the channel it opens, so Back leaves Browse', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.getByRole('navigation', { name: 'Destinations' }).getByRole('link', { name: 'Browse' }).click();
	await expect(page).toHaveURL(`/browse/${LOBBY_ID}`);
	await expect(page.locator('main').getByText(LOBBY_NEWEST)).toBeVisible();
	await page.goBack();
	await expect(page).toHaveURL('/');
});

// ── The channel pane ────────────────────────────────────────────────────────

test('the channel pane lists the text channels under their categories, with their counts', { annotation }, async ({ page }) => {
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	const channels = pane(page);
	await expect(channels.getByRole('heading', { level: 3 })).toHaveText(['Text Channels', 'Media']);
	const groups = channels.locator('.channel-group');
	await expect(groups.nth(0).locator('.channel-name')).toHaveText(['general', 'random', 'lobby']);
	await expect(groups.nth(1).locator('.channel-name')).toHaveText(['art']);
	// Counts from the channel rows; the voice channel and the categories are not rows.
	expect(await paneRows(page)).toEqual(['general 6', 'random 3', 'lobby 123', 'art 3']);
	await expect(channels.getByText('hangout')).toHaveCount(0);
	await expect(channels.locator('.channel-item[aria-current="page"]')).toHaveText(/general/);
});

test('the channel pane filters by name', { annotation }, async ({ page }) => {
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	const filter = pane(page).getByRole('searchbox', { name: 'Filter channels' });
	await filter.fill('AR');
	expect(await paneRows(page)).toEqual(['art 3']);
	await expect(pane(page).getByRole('heading', { level: 3 })).toHaveText(['Media']);

	await filter.fill('nothing like it');
	await expect(pane(page).getByText('No channels match “nothing like it”')).toBeVisible();

	await pane(page).getByRole('button', { name: 'Clear filter' }).click();
	expect(await paneRows(page)).toHaveLength(4);
});

test('picking a channel in the pane opens it in the reader', { annotation }, async ({ page }) => {
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	await pane(page).getByRole('link', { name: /^art/ }).click();
	await expect(page).toHaveURL(`/browse/900000000000000022`);
	const main = page.locator('main');
	await expect(main.getByRole('heading', { level: 1 })).toHaveText('art');
	await expect(main.getByText('Show your drawings')).toBeVisible();
	await expect(main.getByText('Another drawing')).toBeVisible();
});

// ── A message link ──────────────────────────────────────────────────────────

test('a message link opens the feed on that message, marked, with newer ones loading at the bottom', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 800 });
	const requests: string[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (url.pathname === `/api/channels/${LOBBY_ID}/messages`) requests.push(url.search);
	});
	const anchor = lurkerMessage(60);
	await page.goto(`/browse/${LOBBY_ID}?message=${anchor}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');

	await expect(card(page, anchor)).toBeInViewport();
	await expect(card(page, anchor)).toHaveAttribute('aria-current', 'true');
	await expect(card(page, anchor)).toHaveCSS('border-top-color', 'rgb(240, 178, 84)');
	await expect(main.locator('[aria-current="true"]')).toHaveCount(1);
	// A page of 50 around it: 25 up to and including it, 25 after.
	await expect(main.getByText(lurkerText(36), { exact: true })).toBeAttached();
	await expect(main.getByText(lurkerText(35), { exact: true })).toHaveCount(0);
	await expect(main.getByText(lurkerText(85), { exact: true })).toBeAttached();
	await expect(main.getByText(lurkerText(86), { exact: true })).toHaveCount(0);
	expect(requests).toEqual([`?limit=50&around=${anchor}`]);

	// Reaching the bottom loads the newer messages, page by page, up to the newest.
	const newest = main.getByText(LOBBY_NEWEST, { exact: true });
	await expect(async () => {
		await main.evaluate((m) => (m.scrollTop = m.scrollHeight));
		await expect(newest).toBeAttached({ timeout: 500 });
	}).toPass();
	await expect(main.getByRole('button', { name: 'Load newer messages' })).toHaveCount(0);
	await expect(main.getByRole('link', { name: 'Newest messages' })).toHaveCount(0);
	expect(requests[1]).toBe(`?after=${lurkerMessage(85)}&limit=50`);
	await expect(card(page, anchor)).toHaveAttribute('aria-current', 'true');
});

test('a message link loads older messages above it without moving it', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 800 });
	const anchor = lurkerMessage(60);
	await page.goto(`/browse/${LOBBY_ID}?message=${anchor}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	const loadOlder = main.getByRole('button', { name: 'Load older messages' });
	await loadOlder.scrollIntoViewIfNeeded();
	const before = await topOf(page, lurkerText(36));
	await loadOlder.click();
	await expect(main.getByText(lurkerText(1), { exact: true })).toBeAttached();
	await page.waitForLoadState('networkidle');
	expect(Math.abs((await topOf(page, lurkerText(36))) - before)).toBeLessThanOrEqual(3);
	await expect(loadOlder).toHaveCount(0);
});

test('a message link pages both ways one page at a time', { annotation }, async ({ page }) => {
	// Pages of two: the link opens on "Anyone up…" and the one after it.
	await page.setViewportSize({ width: 1280, height: 1000 });
	await narrowPages(page, 2);
	await page.goto(`/browse/${GENERAL_ID}?message=${GAME_ID}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await expect(card(page, GAME_ID)).toBeInViewport();
	await expect(card(page, GAME_ID)).toHaveAttribute('aria-current', 'true');
	await expect(main.getByText('Count me in.', { exact: true })).toBeAttached();

	await main.getByRole('button', { name: 'Load older messages' }).click();
	await expect(main.getByText('Welcome to the smoke test guild!', { exact: true })).toBeAttached();
	await expect(main.getByRole('button', { name: 'Load older messages' })).toHaveCount(0);

	// The bottom of this short feed is in view, so the newer pages load on their own.
	await expect(main.getByText('The hello world of June.', { exact: true })).toBeAttached();
	await expect(main.getByRole('button', { name: 'Load newer messages' })).toHaveCount(0);
	expect(await topOf(page, 'Welcome to the smoke test guild!')).toBeLessThan(
		await topOf(page, 'The hello world of June.')
	);
});

test('Newest messages leaves the message link for the newest page', { annotation }, async ({ page }) => {
	await page.goto(`/browse/${LOBBY_ID}?message=${lurkerMessage(20)}`, { waitUntil: 'networkidle' });
	await page.locator('main').getByRole('link', { name: 'Newest messages' }).click();
	await expect(page).toHaveURL(`/browse/${LOBBY_ID}`);
	await expect(page.locator('main').getByText(LOBBY_NEWEST, { exact: true })).toBeInViewport();
	await expect(page.locator('main [aria-current="true"]')).toHaveCount(0);
});

test('a link to a message the channel does not hold opens at the newest', { annotation }, async ({ page }) => {
	await page.goto(`/browse/${GENERAL_ID}?message=1`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await expect(main.getByText('The hello world of June.', { exact: true })).toBeInViewport();
	await expect(main.locator('[aria-current="true"]')).toHaveCount(0);
	await expect(main.getByRole('button', { name: 'Load newer messages' })).toHaveCount(0);
});

test('a search result opens its message in Browse', { annotation: { type: ROUTE_ANNOTATION, description: '/search' } }, async ({ page }) => {
	await page.goto('/search?q=hello', { waitUntil: 'networkidle' });
	await page.locator('main').getByRole('link', { name: 'general' }).click();
	await expect(page).toHaveURL(`/browse/${GENERAL_ID}?message=${HELLO_ID}`);
	await expect(card(page, HELLO_ID)).toHaveAttribute('aria-current', 'true');
	await expect(card(page, HELLO_ID)).toBeInViewport();
});

// ── Scrolling ───────────────────────────────────────────────────────────────

test('the channel pane scrolls its own list while the feed scrolls the page', { annotation }, async ({ page }) => {
	// Short enough that the pane's list overflows too.
	await page.setViewportSize({ width: 1280, height: 260 });
	await page.goto(`/browse/${LOBBY_ID}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	const list = pane(page).locator('.channel-list');
	const scrollTops = async () => ({
		main: await main.evaluate((m) => m.scrollTop),
		list: await list.evaluate((l) => l.scrollTop)
	});

	// The feed opened at its bottom; the pane stays at the top of the window, full height.
	const opened = await scrollTops();
	expect(opened.main).toBeGreaterThan(0);
	const box = (await pane(page).boundingBox())!;
	expect([box.y, box.height]).toEqual([0, 260]);

	await list.evaluate((l) => (l.scrollTop = l.scrollHeight));
	const listScrolled = await scrollTops();
	expect(listScrolled.list).toBeGreaterThan(0);
	expect(listScrolled.main).toBe(opened.main);

	await main.evaluate((m) => (m.scrollTop = 0));
	expect((await scrollTops()).list).toBe(listScrolled.list);
	expect((await pane(page).boundingBox())!.y).toBe(0);
});

// ── Below 768px ─────────────────────────────────────────────────────────────

test('on a phone, /browse is the channel list and a channel opens the reader alone', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto('/browse', { waitUntil: 'networkidle' });
	await expect(page).toHaveURL('/browse');
	expect(await paneRows(page)).toHaveLength(4);

	await pane(page).getByRole('link', { name: /^general/ }).click();
	await expect(page).toHaveURL(`/browse/${GENERAL_ID}`);
	await expect(pane(page)).toBeHidden();
	const main = page.locator('main');
	await expect(main.getByText('The hello world of June.', { exact: true })).toBeInViewport();
	const mainBox = (await main.boundingBox())!;
	expect(await main.evaluate((m) => m.scrollWidth <= m.clientWidth)).toBe(true);
	expect(mainBox.width).toBeLessThanOrEqual(390);

	await main.getByRole('link', { name: 'Channels' }).click();
	await expect(page).toHaveURL('/browse');
	await expect(pane(page)).toBeVisible();
});
