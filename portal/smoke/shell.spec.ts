// The shell every route shares (#58): its tab icon, the sidebar with its five
// destinations, rail, version badge and archive-status card, and the one scroll
// container page content lives in, which keeps each screen's scroll position.
import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures.ts';

const portalPackage = JSON.parse(
	readFileSync(new URL('../package.json', import.meta.url), 'utf8')
) as { version: string };

// Ids and text from tests/smoke_archive.py.
const GENERAL_ID = '900000000000000020';
const LOBBY_ID = '900000000000000023';

test('the tab shows the Wumpus Archiver favicon', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const href = await page.locator('link[rel="icon"]').getAttribute('href');
	expect(href).toBeTruthy();

	const icon = await page.request.get(new URL(href!, page.url()).href);
	expect(icon.status()).toBe(200);
	expect(icon.headers()['content-type']).toContain('image/svg+xml');
	const svg = await icon.text();
	expect(svg).toContain('<title>Wumpus Archiver</title>');
	expect(svg).not.toContain('svelte-logo');
});

test("the version badge shows the portal's package version", async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await expect(page.locator('.sidebar .version')).toHaveText(`v${portalPackage.version}`);
});

// ── The sidebar ─────────────────────────────────────────────────────────────

test('the sidebar holds the five destinations, and the Archive screen is not one of them', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const nav = page.getByRole('navigation', { name: 'Destinations' });
	await expect(nav.getByRole('link')).toHaveText(['Overview', 'Browse', 'Media', 'Search', 'People']);
	await expect(nav.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page');

	for (const [name, url, heading] of [
		// Browse opens the guild's most active channel.
		['Browse', `/browse/${LOBBY_ID}`, 'lobby'],
		['Media', '/media', 'Media'],
		['Search', '/search', 'Search'],
		['People', '/people', 'People'],
		['Overview', '/', 'Smoke Test Guild']
	]) {
		await nav.getByRole('link', { name }).click();
		await expect(page).toHaveURL(url);
		await expect(page.locator('main h1').first()).toHaveText(heading);
		await expect(nav.getByRole('link', { name })).toHaveAttribute('aria-current', 'page');
	}
});

/** The sidebar's width, once its collapse or expand has finished. */
async function sidebarWidth(page: Page): Promise<number> {
	const sidebar = page.getByRole('complementary', { name: 'Sidebar' });
	await sidebar.evaluate((el) => Promise.all(el.getAnimations().map((a) => a.finished)));
	return (await sidebar.boundingBox())!.width;
}

test('Ctrl+\\ collapses the sidebar to its icon rail and back, and the choice survives a reload', async ({ page }) => {
	await page.setViewportSize({ width: 1440, height: 900 });
	await page.goto('/', { waitUntil: 'networkidle' });
	expect(await sidebarWidth(page)).toBe(240);
	const label = page.getByRole('navigation', { name: 'Destinations' }).getByText('Browse');
	await expect(label).toHaveCSS('opacity', '1');

	await page.keyboard.press('Control+Backslash');
	expect(await sidebarWidth(page)).toBe(64);
	await expect(label).toHaveCSS('opacity', '0');
	// The content takes the room the sidebar gave up.
	expect((await page.locator('main').boundingBox())!.x).toBe(64);

	await page.reload({ waitUntil: 'networkidle' });
	expect(await sidebarWidth(page)).toBe(64);

	await page.getByRole('button', { name: /^Expand sidebar/ }).click();
	expect(await sidebarWidth(page)).toBe(240);
	await page.reload({ waitUntil: 'networkidle' });
	expect(await sidebarWidth(page)).toBe(240);
});

test('on the rail, an item shows its name as a tooltip after a pause', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.keyboard.press('Control+Backslash');
	await sidebarWidth(page);

	const browse = page.getByRole('navigation', { name: 'Destinations' }).getByRole('link', { name: 'Browse' });
	await browse.hover();
	const tooltip = page.getByRole('tooltip');
	await expect(tooltip).toHaveCount(0);
	await expect(tooltip).toHaveText('Browse');
	const [tip, item] = [(await tooltip.boundingBox())!, (await browse.boundingBox())!];
	expect(tip.x).toBeGreaterThanOrEqual(item.x + item.width);

	await page.mouse.move(800, 400);
	await expect(tooltip).toHaveCount(0);
});

test('expanded, the sidebar shows no tooltips', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.getByRole('navigation', { name: 'Destinations' }).getByRole('link', { name: 'Browse' }).hover();
	await page.waitForTimeout(700);
	await expect(page.getByRole('tooltip')).toHaveCount(0);
});

test('with reduced motion, the sidebar changes width without animating it', async ({ page }) => {
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await page.goto('/', { waitUntil: 'networkidle' });
	const sidebar = page.getByRole('complementary', { name: 'Sidebar' });
	await page.keyboard.press('Control+Backslash');
	const moving = await sidebar.evaluate((el) =>
		el.getAnimations().map((a) => (a as CSSTransition).transitionProperty ?? (a as CSSAnimation).animationName)
	);
	expect(moving).not.toContain('width');
	expect((await sidebar.boundingBox())!.width).toBe(64);
});

test('the guild switcher lists every guild and marks the selected one', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const trigger = page.getByRole('button', { name: 'Guild: Smoke Test Guild' });
	await trigger.click();
	const list = page.getByRole('listbox', { name: 'Guilds' });
	await expect(list.getByRole('option')).toHaveCount(2);
	await expect(list.getByRole('option', { selected: true })).toContainText('Smoke Test Guild');
	await expect(list).toBeFocused();

	await page.keyboard.press('Escape');
	await expect(list).toHaveCount(0);
	await expect(trigger).toBeFocused();
});

// ── The archive-status card ─────────────────────────────────────────────────

/** Answer scrape status as the real server would with a job scraping #general. */
async function runningJob(page: Page): Promise<void> {
	await page.route('**/api/scrape/status', async (route) => {
		const real = await (await route.fetch()).json();
		await route.fulfill({
			json: {
				...real,
				busy: true,
				current_job: {
					id: 'smoke-job',
					guild_id: '1',
					status: 'scraping',
					progress: {
						current_channel: 'general',
						channels_done: 1,
						messages_scraped: 12,
						attachments_found: 4,
						errors: []
					},
					started_at: '2026-01-01T00:00:00Z',
					completed_at: null,
					result: null,
					error_message: null,
					duration_seconds: 4
				}
			}
		});
	});
}

test('the archive-status card says the archive is idle and opens the Archive screen', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const card = page.getByRole('link', { name: /^Archive screen:/ });
	await expect(card).toHaveAttribute('data-state', 'idle');
	await expect(card).toContainText('Archive idle');
	await expect(card).toContainText('Scraped Jun 29, 2024');

	await card.click();
	await expect(page).toHaveURL('/archive');
	await expect(page.locator('main h1')).toHaveText('Archive');
	await expect(card).toHaveAttribute('aria-current', 'page');
});

test('the archive-status card shows a running scrape job on every screen', async ({ page }) => {
	await runningJob(page);
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'domcontentloaded' });
	const card = page.getByRole('link', { name: /^Archive screen:/ });
	await expect(card).toHaveAttribute('data-state', 'running');
	await expect(card).toContainText('Scraping');
	await expect(card).toContainText('#general · 12 messages');
	await expect(card).toHaveAttribute('href', '/archive');
});

// ── The scroll container ────────────────────────────────────────────────────

// A screen and text in its content; the content's scroll container is checked from it.
const SCREENS: [string, string][] = [
	['/', 'Most Active Channels'],
	['/browse', 'aaron checks in, 2 of 2.'],
	[`/browse/${GENERAL_ID}`, 'The hello world of June.'],
	['/search?q=hello', 'The hello world of June.'],
	['/media', 'May 2024'],
	['/people', 'Lurker 001'],
	['/people/900000000000000100', 'Alice'],
	['/archive', 'Attachments on disk']
];

for (const [url, text] of SCREENS) {
	test(`${url} scrolls its content in the shell's one scroll container`, async ({ page }) => {
		await page.setViewportSize({ width: 1280, height: 600 });
		await page.goto(url, { waitUntil: 'networkidle' });
		const content = page.locator('main').getByText(text, { exact: true }).first();
		await expect(content).toBeVisible();
		const scrollers = await content.evaluate((el) => {
			const found: string[] = [];
			for (let node = el.parentElement; node; node = node.parentElement) {
				if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) {
					found.push(`${node.tagName.toLowerCase()}${node.id ? `#${node.id}` : ''}.${node.className}`);
				}
			}
			const doc = document.scrollingElement!;
			return { found, documentScrolls: doc.scrollHeight > doc.clientHeight };
		});
		expect(scrollers.found).toHaveLength(1);
		expect(scrollers.found[0]).toMatch(/^main#shell-scroller\b/);
		expect(scrollers.documentScrolls).toBe(false);
	});
}

test('back and forward restore each screen’s scroll position', async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 600 });
	await page.goto('/people', { waitUntil: 'networkidle' });
	const main = page.locator('main');
	const scrollTop = () => main.evaluate((m) => m.scrollTop);

	await main.evaluate((m) => (m.scrollTop = 1500));
	expect(await scrollTop()).toBe(1500);
	// A row wholly in view, so clicking it scrolls nothing.
	const index = await main.evaluate((m) => {
		const view = m.getBoundingClientRect();
		const rows = [...m.querySelectorAll('.person-row')];
		return rows.findIndex((r) => r.getBoundingClientRect().top > view.top + 100);
	});
	await main.locator('.person-row').nth(index).click();
	await expect(page).toHaveURL(/\/people\/\d+$/);
	await expect(main.getByText('Recent messages')).toBeVisible();
	await expect.poll(scrollTop).toBe(0);
	await main.evaluate((m) => (m.scrollTop = 120));
	const profileTop = await scrollTop();
	expect(profileTop).toBeGreaterThan(0);

	await page.goBack();
	await expect(page).toHaveURL('/people');
	await expect.poll(scrollTop).toBe(1500);

	await page.goForward();
	await expect(page).toHaveURL(/\/people\/\d+$/);
	await expect.poll(scrollTop).toBe(profileTop);
});

test('a new screen opens at the top', async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 600 });
	await page.goto('/people', { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await main.evaluate((m) => (m.scrollTop = 900));
	await page.getByRole('navigation', { name: 'Destinations' }).getByRole('link', { name: 'Overview' }).click();
	await expect(page).toHaveURL('/');
	await expect.poll(() => main.evaluate((m) => m.scrollTop)).toBe(0);
});

test("the reader's header and Browse's channel pane stay in view as the content scrolls", async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 540 });
	for (const [url, selector] of [
		[`/browse/${GENERAL_ID}`, '.reader-header'],
		[`/browse/${GENERAL_ID}`, '.channel-pane']
	]) {
		await page.goto(url, { waitUntil: 'networkidle' });
		const main = page.locator('main');
		const pinned = main.locator(selector);
		// The reader opens at the bottom of a feed taller than the window.
		expect(await main.evaluate((m) => m.scrollTop)).toBeGreaterThan(0);
		expect((await pinned.boundingBox())!.y).toBe(0);
		await main.evaluate((m) => (m.scrollTop = 0));
		expect((await pinned.boundingBox())!.y).toBe(0);
	}
});

test('content cross-fades between screens, by opacity alone, while the sidebar stays', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const fades = page.evaluate(
		() =>
			new Promise<{ pseudo: string; properties: string[] }[]>((resolve) => {
				const seen = new Map<string, Set<string>>();
				const until = performance.now() + 3_000;
				const look = () => {
					for (const animation of document.getAnimations()) {
						const effect = animation.effect as KeyframeEffect | null;
						const pseudo = effect?.pseudoElement;
						if (!pseudo?.startsWith('::view-transition')) continue;
						const properties = seen.get(pseudo) ?? new Set<string>();
						for (const frame of effect!.getKeyframes()) {
							for (const key of Object.keys(frame)) {
								if (!['offset', 'easing', 'composite', 'computedOffset'].includes(key)) properties.add(key);
							}
						}
						seen.set(pseudo, properties);
					}
					if (seen.size > 0 && document.getAnimations().length === 0) {
						resolve([...seen].map(([p, s]) => ({ pseudo: p, properties: [...s] })));
					} else if (performance.now() > until) {
						resolve([...seen].map(([p, s]) => ({ pseudo: p, properties: [...s] })));
					} else {
						requestAnimationFrame(look);
					}
				};
				requestAnimationFrame(look);
			})
	);
	await page.getByRole('navigation', { name: 'Destinations' }).getByRole('link', { name: 'People' }).click();
	const animated = await fades;
	expect(animated.map((a) => a.pseudo).sort()).toEqual([
		'::view-transition-new(page)',
		'::view-transition-old(page)'
	]);
	// The cross-fade blends the two images (mix-blend-mode); nothing moves or resizes.
	for (const { properties } of animated) {
		expect(properties.filter((p) => p !== 'mixBlendMode')).toEqual(['opacity']);
	}
});
