// Browse's reader detail and jump rail (#61): the feed groups one author's messages
// within 5 minutes under one header, separates days with sticky date pills, shows what a
// reply answers and follows it there, prints no raw ids, and offers each message's
// actions on hover or focus. The jump rail lists the channel's months and opens the
// reader at a month's first message; J/K move between messages and G then L goes to
// the newest.
import type { Locator, Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';
import { narrowPages, said, topOf } from './reader.ts';

// Ids and text from tests/smoke_archive.py.
const GENERAL_ID = '900000000000000020';
const LOBBY_ID = '900000000000000023';
const ART_ID = '900000000000000022';
/** general's messages, oldest first: ids 900000000000001000 + their index in the seed. */
const WELCOME = '900000000000001000';
const THANKS = '900000000000001001';
const GAME = '900000000000001002';
const COUNT_ME_IN = '900000000000001003';
const JUNE_ALREADY = '900000000000001008';
const HELLO = '900000000000001009';
/** Zara's three messages in #lobby, 2 minutes apart, then aaron's two, 10 minutes apart. */
const ZARA = ['900000000000006500', '900000000000006501', '900000000000006502'];
const AARON = ['900000000000006503', '900000000000006504'];
const LOBBY_NEWEST = 'aaron checks in, 2 of 2.';
const lurkerMessage = (n: number) => String(900000000000003000n + BigInt(n - 1));

const annotation = { type: ROUTE_ANNOTATION, description: '/browse/[channel]' };

function row(page: Page, id: string): Locator {
	return page.locator(`main [data-message-id="${id}"]`);
}

function rail(page: Page): Locator {
	return page.getByRole('navigation', { name: 'Jump to a month' });
}

/** The bottom of the reader's sticky header, in viewport pixels. */
async function headerBottom(page: Page): Promise<number> {
	const box = (await page.locator('main header').boundingBox())!;
	return box.y + box.height;
}

/** Whether message `id` is scrolled away above the view, under the header or beyond. */
async function above(page: Page, id: string): Promise<boolean> {
	const box = (await row(page, id).boundingBox())!;
	return box.y + box.height <= (await headerBottom(page)) + 1;
}

/** The id of the message row that has the keyboard focus, or null. */
function focusedMessage(page: Page): Promise<string | null> {
	return page.evaluate(() => (document.activeElement as HTMLElement | null)?.dataset.messageId ?? null);
}

// ── Grouping ────────────────────────────────────────────────────────────────

test('one author’s messages 2 minutes apart share a header; 10 minutes apart each have one', { annotation }, async ({ page }) => {
	await page.goto(`/browse/${LOBBY_ID}`, { waitUntil: 'networkidle' });
	// Zara: one group, her name and avatar once.
	await expect(row(page, ZARA[0]).locator('.author')).toHaveText('Zara');
	for (const id of ZARA.slice(1)) {
		await expect(row(page, id)).toHaveClass(/continuation/);
		await expect(row(page, id).locator('.author')).toHaveCount(0);
		await expect(row(page, id).locator('img, .avatar')).toHaveCount(0);
	}
	// aaron: two groups, each with its header.
	for (const id of AARON) {
		await expect(row(page, id)).not.toHaveClass(/continuation/);
		await expect(row(page, id).locator('.author')).toHaveText('aaron');
	}
	// A continuation shows its time on hover, in the gutter.
	const gutterTime = row(page, ZARA[1]).locator('.gutter-time');
	await expect(gutterTime).toHaveCSS('opacity', '0');
	await row(page, ZARA[1]).hover();
	await expect(gutterTime).toHaveCSS('opacity', '1');
});

test('days are separated by date pills that stick below the header', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 400 });
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	const pills = main.locator('[role="feed"] .pill');
	await expect(pills).toHaveText(['Monday, May 20, 2024', 'Sunday, June 9, 2024', 'Friday, June 21, 2024']);

	// Scrolled into May 20, below its first message, the day's pill stays in view.
	await row(page, COUNT_ME_IN).evaluate((el) => el.scrollIntoView({ block: 'start' }));
	expect(await above(page, WELCOME)).toBe(true);
	const pill = (await pills.first().boundingBox())!;
	const top = await headerBottom(page);
	expect(pill.y).toBeGreaterThanOrEqual(top);
	expect(pill.y).toBeLessThanOrEqual(top + 12);
});

// ── Replies ─────────────────────────────────────────────────────────────────

test('a reply shows who and what it answers, and clicking it scrolls to that message', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 400 });
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	const reply = row(page, THANKS).getByRole('link', { name: /^Replying to Alice/ });
	await expect(reply).toHaveText(/Alice\s*Welcome to the smoke test guild!/);
	await expect(reply).toHaveAttribute('href', `/browse/${GENERAL_ID}?message=${WELCOME}`);

	expect(await above(page, WELCOME)).toBe(true);
	await reply.click();
	await expect(row(page, WELCOME)).toBeInViewport();
	await expect(row(page, WELCOME)).toHaveClass(/flash/);
	expect(await focusedMessage(page)).toBe(WELCOME);
	// In place: the reader did not navigate.
	await expect(page).toHaveURL(`/browse/${GENERAL_ID}`);
});

test('a reply to a message that is not loaded opens it in context', { annotation }, async ({ page }) => {
	// Pages of two: the link opens on "Thanks…" and the one after it, not on the welcome.
	await narrowPages(page, 2);
	await page.goto(`/browse/${GENERAL_ID}?message=${THANKS}`, { waitUntil: 'networkidle' });
	await expect(row(page, WELCOME)).toHaveCount(0);
	await row(page, THANKS).getByRole('link', { name: /^Replying to Alice/ }).click();
	await expect(page).toHaveURL(`/browse/${GENERAL_ID}?message=${WELCOME}`);
	await expect(row(page, WELCOME)).toHaveAttribute('aria-current', 'true');
});

// ── No raw ids ──────────────────────────────────────────────────────────────

for (const [name, id] of [
	['general', GENERAL_ID],
	['lobby', LOBBY_ID],
	['art', ART_ID]
]) {
	test(`no message row in #${name} prints a raw id`, { annotation }, async ({ page }) => {
		await page.goto(`/browse/${id}`, { waitUntil: 'networkidle' });
		const rows = page.locator('main [data-message-id]');
		expect(await rows.count()).toBeGreaterThan(0);
		for (const text of await rows.allInnerTexts()) {
			expect(text).not.toMatch(/\d{15,}/);
		}
	});
}

// ── Hover actions ───────────────────────────────────────────────────────────

test('a message’s actions rise in on hover and on keyboard focus, and copy its link', { annotation }, async ({ page, context, baseURL }) => {
	await context.grantPermissions(['clipboard-read', 'clipboard-write']);
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	const actions = (id: string) => row(page, id).getByRole('toolbar', { name: 'Message actions' });
	await expect(actions(HELLO)).toHaveCSS('opacity', '0');

	await row(page, HELLO).hover();
	await expect(actions(HELLO)).toHaveCSS('opacity', '1');
	await expect(actions(HELLO).getByRole('link', { name: 'Open in context' })).toHaveAttribute(
		'href',
		`/browse/${GENERAL_ID}?message=${HELLO}`
	);
	await actions(HELLO).getByRole('button', { name: 'Copy link' }).click();
	await expect(actions(HELLO).getByRole('button', { name: 'Link copied' })).toBeVisible();
	const copied = await page.evaluate(() => navigator.clipboard.readText());
	expect(copied).toBe(`${baseURL}/browse/${GENERAL_ID}?message=${HELLO}`);

	// Keyboard focus shows them too.
	await page.mouse.move(0, 0);
	await page.locator('main header').click();
	await page.keyboard.press('j');
	const focused = (await focusedMessage(page))!;
	await expect(actions(focused)).toHaveCSS('opacity', '1');
});

// ── Keys ────────────────────────────────────────────────────────────────────

test('J and K move the focus from message to message, with a visible ring', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 1000 });
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	// The whole channel is in view: J starts at its first message.
	await page.keyboard.press('j');
	expect(await focusedMessage(page)).toBe(WELCOME);
	await expect(row(page, WELCOME)).toHaveCSS('outline-style', 'solid');
	await page.keyboard.press('j');
	expect(await focusedMessage(page)).toBe(THANKS);
	await page.keyboard.press('j');
	expect(await focusedMessage(page)).toBe(GAME);
	await page.keyboard.press('k');
	expect(await focusedMessage(page)).toBe(THANKS);
	// The focused row is the feed's one tab stop (roving focus).
	await expect(row(page, THANKS)).toHaveAttribute('tabindex', '0');
	await expect(row(page, GAME)).toHaveAttribute('tabindex', '-1');

	// Typing in a field types: the keys do not move the focus.
	const filter = page.getByRole('searchbox', { name: 'Filter channels' });
	await filter.click();
	await page.keyboard.type('jk');
	await expect(filter).toHaveValue('jk');
	await expect(filter).toBeFocused();
});

test('J at the bottom of a feed that stops short of the newest loads the next page', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 1000 });
	await narrowPages(page, 2);
	await page.goto(`/browse/${GENERAL_ID}?message=${GAME}`, { waitUntil: 'networkidle' });
	await row(page, COUNT_ME_IN).focus();
	await page.keyboard.press('j');
	expect(await focusedMessage(page)).toBe(JUNE_ALREADY);
});

test('G then L goes to the newest messages', { annotation }, async ({ page }) => {
	await page.goto(`/browse/${LOBBY_ID}?message=${lurkerMessage(20)}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await expect(said(main, LOBBY_NEWEST)).toHaveCount(0);
	await page.keyboard.press('g');
	await page.keyboard.press('l');
	await expect(page).toHaveURL(`/browse/${LOBBY_ID}`);
	await expect(said(main, LOBBY_NEWEST)).toBeInViewport();
	// L alone does nothing.
	await main.evaluate((m) => (m.scrollTop = 0));
	await page.keyboard.press('l');
	await expect(said(main, LOBBY_NEWEST)).not.toBeInViewport();
});

// ── The jump rail ───────────────────────────────────────────────────────────

test('the jump rail lists the channel’s years and months with their counts', { annotation }, async ({ page }) => {
	// Tall enough for the whole channel, so its first message is at the top.
	await page.setViewportSize({ width: 1280, height: 1000 });
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	const months = rail(page).getByRole('button');
	expect(await months.evaluateAll((buttons) => buttons.map((b) => b.getAttribute('aria-label')))).toEqual([
		'May 2024, 4 messages',
		'June 2024, 2 messages'
	]);
	await expect(rail(page).getByRole('heading', { level: 3 })).toHaveText(['2024 6']);
	// The month of the message at the top of the view is marked.
	await expect(rail(page).getByRole('button', { name: 'May 2024, 4 messages' })).toHaveAttribute(
		'aria-current',
		'location'
	);
	await expect(rail(page).locator('[aria-current]')).toHaveCount(1);
});

test('picking a month puts its first message at the top of the view', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 700 });
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');

	await rail(page).getByRole('button', { name: 'June 2024, 2 messages' }).click();
	// May's last message is scrolled away above June's first.
	await expect.poll(() => above(page, COUNT_ME_IN)).toBe(true);
	await expect(row(page, JUNE_ALREADY)).toBeInViewport();
	const top = await headerBottom(page);
	const june = await topOf(page, 'June already?');
	expect(june - top).toBeGreaterThan(0);
	expect(june - top).toBeLessThan(80);

	await rail(page).getByRole('button', { name: 'May 2024, 4 messages' }).click();
	await expect(said(main, 'Welcome to the smoke test guild!')).toBeInViewport();
	await expect
		.poll(async () => (await topOf(page, 'Welcome to the smoke test guild!')) - top)
		.toBeLessThan(80);
	await expect(rail(page).getByRole('button', { name: 'May 2024, 4 messages' })).toHaveAttribute(
		'aria-current',
		'location'
	);
});

test('picking a month in a long channel reads the page around its first message, and G then L returns', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 700 });
	const requests: string[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (url.pathname === `/api/channels/${LOBBY_ID}/messages`) requests.push(url.search);
	});
	await page.goto(`/browse/${LOBBY_ID}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await rail(page).getByRole('button', { name: 'June 2024, 123 messages' }).click();
	await expect(said(main, 'Lurker 001 says hi.')).toBeInViewport();
	expect(requests.at(-1)).toBe(`?limit=50&around=${lurkerMessage(1)}`);
	const top = await headerBottom(page);
	await expect.poll(async () => (await topOf(page, 'Lurker 001 says hi.')) - top).toBeLessThan(80);
	await expect(page).toHaveURL(`/browse/${LOBBY_ID}`);

	// The newest messages, in place.
	await page.keyboard.press('g');
	await page.keyboard.press('l');
	await expect(said(main, LOBBY_NEWEST)).toBeInViewport();
	await expect(page).toHaveURL(`/browse/${LOBBY_ID}`);
});

test('the jump rail is sticky beside the feed', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 1440, height: 600 });
	await page.goto(`/browse/${LOBBY_ID}`, { waitUntil: 'networkidle' });
	const before = (await rail(page).boundingBox())!;
	await page.locator('main').evaluate((m) => (m.scrollTop = 0));
	const after = (await rail(page).boundingBox())!;
	expect(after.y).toBe(before.y);
	expect(before.y).toBeGreaterThanOrEqual(await headerBottom(page) - 1);
});

test('on a phone the reader has no jump rail', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	await expect(said(page.locator('main'), 'The hello world of June.')).toBeInViewport();
	await expect(rail(page)).toBeHidden();
});
