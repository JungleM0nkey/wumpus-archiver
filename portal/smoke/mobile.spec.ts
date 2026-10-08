// The shell below 768px (#59, audit #15): a top bar, a bottom tab bar that carries the
// five destinations, and the sidebar as a sheet. No screen hides a control there: every
// one stays visible and within reach, if need be in a strip that scrolls sideways.
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures.ts';

// Ids from tests/smoke_archive.py.
const ALICE_ID = '900000000000000100';
const NIGHT_GUILD_ID = '900000000000000002';

const PHONE = { width: 390, height: 844 };

// Each screen, and text that shows it has loaded.
const SCREENS: [string, string][] = [
	['/', 'Most Active Channels'],
	['/browse', 'general'],
	['/browse/900000000000000020', 'The hello world of June.'],
	['/search?q=hello', 'The hello world of June.'],
	['/media', 'May 2024'],
	['/people', 'Lurker 001'],
	[`/people/${ALICE_ID}`, 'Alice'],
	['/archive', 'Attachments on disk']
];

test.beforeEach(async ({ page }) => {
	await page.setViewportSize(PHONE);
});

const tabBar = (page: Page) => page.getByRole('navigation', { name: 'Tab bar' });
const sheet = (page: Page) => page.getByRole('dialog', { name: 'Menu' });

test('the tab bar carries the five destinations, and each one opens', async ({ page }) => {
	await page.goto('/archive', { waitUntil: 'networkidle' });
	await expect(tabBar(page).getByRole('link')).toHaveText(['Overview', 'Browse', 'Media', 'Search', 'People']);
	// The sidebar is not on the page until the menu opens it.
	await expect(page.getByRole('complementary', { name: 'Sidebar' })).toBeHidden();

	// Each destination and a heading it shows; Browse shows its channel list first.
	for (const [name, url, heading] of [
		['Overview', '/', 'Smoke Test Guild'],
		['Browse', '/browse', 'Channels'],
		['Media', '/media', 'Media'],
		['Search', '/search', 'Search'],
		['People', '/people', 'People']
	]) {
		const tab = tabBar(page).getByRole('link', { name });
		const box = (await tab.boundingBox())!;
		expect(box.y + box.height).toBeLessThanOrEqual(PHONE.height);
		await tab.click();
		await expect(page).toHaveURL(url);
		await expect(page.locator('main').getByRole('heading', { name: heading }).first()).toBeVisible();
		await expect(tab).toHaveAttribute('aria-current', 'page');
	}
});

test('the content fills the room between the top bar and the tab bar', async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	const top = (await page.getByRole('button', { name: 'Open menu' }).boundingBox())!;
	const main = (await page.locator('main').boundingBox())!;
	const tabs = (await tabBar(page).boundingBox())!;
	expect(top.y).toBeLessThan(main.y);
	expect(main.y + main.height).toBe(tabs.y);
	expect(tabs.y + tabs.height).toBe(PHONE.height);
	const viewportHeight = await page
		.locator('main')
		.evaluate((m) => {
			const probe = document.createElement('div');
			probe.style.height = 'var(--shell-viewport-height)';
			m.append(probe);
			const height = probe.getBoundingClientRect().height;
			probe.remove();
			return height;
		});
	expect(viewportHeight).toBe(main.height);
});

test('at 1440px there is no top bar or tab bar', async ({ page }) => {
	await page.setViewportSize({ width: 1440, height: 900 });
	await page.goto('/', { waitUntil: 'networkidle' });
	await expect(tabBar(page)).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Open menu' })).toHaveCount(0);
	await expect(page.getByRole('complementary', { name: 'Sidebar' })).toBeVisible();
});

test('the menu opens the sidebar as a sheet that keeps focus, and Esc gives it back', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const menu = page.getByRole('button', { name: 'Open menu' });
	await menu.click();
	const dialog = sheet(page);
	await expect(dialog).toBeVisible();
	await expect(menu).toHaveAttribute('aria-expanded', 'true');

	// The guild switcher, search, the destinations and the archive status.
	await expect(dialog.getByRole('button', { name: 'Guild: Smoke Test Guild' })).toBeVisible();
	await expect(dialog.getByRole('searchbox', { name: 'Search messages' })).toBeVisible();
	await expect(dialog.getByRole('navigation', { name: 'Destinations' }).getByRole('link')).toHaveText([
		'Overview',
		'Browse',
		'Media',
		'Search',
		'People'
	]);
	await expect(dialog.getByRole('link', { name: /^Archive screen:/ })).toBeVisible();
	// Expanded, not the rail.
	await expect(dialog.getByRole('navigation', { name: 'Destinations' }).getByText('Browse')).toHaveCSS('opacity', '1');

	for (let i = 0; i < 14; i++) {
		await page.keyboard.press(i % 4 === 3 ? 'Shift+Tab' : 'Tab');
		expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
	}
	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
	await expect(menu).toBeFocused();
	await expect(menu).toHaveAttribute('aria-expanded', 'false');
});

test('a destination in the sheet opens and closes the sheet', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.getByRole('button', { name: 'Open menu' }).click();
	await sheet(page).getByRole('link', { name: 'People' }).click();
	await expect(page).toHaveURL('/people');
	await expect(sheet(page)).toBeHidden();

	await page.getByRole('button', { name: 'Open menu' }).click();
	await sheet(page).getByRole('link', { name: /^Archive screen:/ }).click();
	await expect(page).toHaveURL('/archive');
	await expect(sheet(page)).toBeHidden();
});

test("the sheet's search and guild switcher work, and its close button closes it", async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.getByRole('button', { name: 'Open menu' }).click();
	await sheet(page).getByRole('searchbox', { name: 'Search messages' }).fill('hello');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL('/search?q=hello');
	await expect(sheet(page)).toBeHidden();

	await page.getByRole('button', { name: 'Open menu' }).click();
	// Opened while the sheet may still be sliding in, the list still opens under its trigger.
	const trigger = sheet(page).getByRole('button', { name: 'Guild: Smoke Test Guild' });
	await trigger.click();
	const list = sheet(page).getByRole('listbox', { name: 'Guilds' });
	await expect(list).toBeInViewport({ ratio: 1 });
	const [under, over] = [(await list.boundingBox())!, (await trigger.boundingBox())!];
	expect(Math.round(under.x)).toBe(Math.round(over.x));
	await sheet(page).getByRole('option', { name: /Night Owls/ }).click();
	await expect(page).toHaveURL(`/search?q=hello&guild=${NIGHT_GUILD_ID}`);
	await expect(sheet(page)).toBeHidden();

	await page.getByRole('button', { name: 'Open menu' }).click();
	await sheet(page).getByRole('button', { name: 'Close menu' }).click();
	await expect(sheet(page)).toBeHidden();
});

test('the top bar opens the command palette', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.getByRole('button', { name: 'Search or jump to' }).click();
	const palette = page.getByRole('dialog', { name: 'Command palette' });
	await expect(palette).toBeVisible();
	// A touch closes it from its Close button.
	await palette.getByRole('button', { name: 'Close' }).click();
	await expect(palette).toBeHidden();

	await page.getByRole('button', { name: 'Search or jump to' }).click();
	await palette.getByRole('combobox').fill('art');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL('/browse/900000000000000022');
});

test('with reduced motion, the sheet fades in without sliding', async ({ page }) => {
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.evaluate(() => {
		const seen: string[] = [];
		(window as unknown as { seen: string[] }).seen = seen;
		document.addEventListener('animationstart', (event) => {
			const target = event.target as Element;
			if (target.id !== 'shell-sheet' || event.pseudoElement) return;
			for (const animation of target.getAnimations()) {
				for (const frame of (animation.effect as KeyframeEffect).getKeyframes()) {
					seen.push(...Object.keys(frame).filter((k) => !['offset', 'easing', 'composite', 'computedOffset'].includes(k)));
				}
			}
		});
	});
	await page.getByRole('button', { name: 'Open menu' }).click();
	await expect(sheet(page)).toBeVisible();
	expect([...new Set(await page.evaluate(() => (window as unknown as { seen: string[] }).seen))]).toEqual(['opacity']);
});

/**
 * Panes a narrow screen shows one at a time, by screen: a selector for the pane hidden
 * there, and the visible control that leads to it. Their controls are a step away, not gone.
 */
const OTHER_PANES: Record<string, { pane: string; via: string }> = {
	// The channel list: picking a channel opens its reader.
	'/browse': { pane: '.browse-main', via: '.channel-pane a[href^="/browse/"]' },
	// The reader: its back link opens the channel list.
	'/browse/900000000000000020': { pane: '.channel-pane', via: '.back-link' }
};

/**
 * The controls in a screen's content that a reader cannot reach: hidden (display:none,
 * visibility:hidden) other than in a collapsed region a visible control expands
 * (aria-controls, aria-expanded) or in another pane (OTHER_PANES), or outside the
 * viewport's width with no strip to scroll them into view.
 */
async function unreachableControls(page: Page, url: string): Promise<string[]> {
	return page.locator('main').evaluate((main, other) => {
		const width = document.documentElement.clientWidth;
		const controls = main.querySelectorAll<HTMLElement>(
			'a[href], button, input, select, textarea, [role="tab"], [role="button"], [tabindex]:not([tabindex="-1"])'
		);
		const visible = (el: Element | null) => !!el && el.checkVisibility({ checkVisibilityCSS: true });
		/** The nearest ancestor inside main that scrolls sideways and has room to. */
		const strip = (el: HTMLElement) => {
			for (let node = el.parentElement; node && node !== main; node = node.parentElement) {
				if (/(auto|scroll)/.test(getComputedStyle(node).overflowX) && node.scrollWidth > node.clientWidth) {
					return node;
				}
			}
			return null;
		};
		/** Whether `el` is in a collapsed region that a visible control expands. */
		const collapsed = (el: HTMLElement) => {
			for (let node = el.parentElement; node && node !== main; node = node.parentElement) {
				if (!node.id) continue;
				const toggle = main.querySelector(`[aria-controls="${CSS.escape(node.id)}"][aria-expanded="false"]`);
				if (visible(toggle)) return true;
			}
			return false;
		};
		const inOtherPane = (el: HTMLElement) =>
			!!other && !!el.closest(other.pane) && visible(main.querySelector(other.via));
		return [...controls].flatMap((el) => {
			const name = `${el.tagName.toLowerCase()} "${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 40)}"`;
			if (!visible(el)) return collapsed(el) || inOtherPane(el) ? [] : [`${name} is hidden`];
			const box = el.getBoundingClientRect();
			const within = (b: DOMRect) => b.left >= -1 && b.right <= width + 1;
			if (within(box)) return [];
			const scroller = strip(el);
			if (scroller && within(scroller.getBoundingClientRect())) return [];
			return [`${name} is outside the viewport (${Math.round(box.left)}..${Math.round(box.right)})`];
		});
	}, OTHER_PANES[url] ?? null);
}

for (const [url, text] of SCREENS) {
	test(`at 390×844 every control on ${url} is within reach`, async ({ page }) => {
		await page.goto(url, { waitUntil: 'networkidle' });
		await expect(page.locator('main').getByText(text, { exact: true }).first()).toBeAttached();
		expect(await unreachableControls(page, url)).toEqual([]);
		// Nothing makes the content wider than the phone.
		const main = page.locator('main');
		expect(await main.evaluate((m) => m.scrollWidth - m.clientWidth)).toBe(0);
	});
}

test("on Browse the reader's jump rail opens from its toggle and jumps", async ({ page }) => {
	await page.goto('/browse/900000000000000020', { waitUntil: 'networkidle' });
	const toggle = page.locator('main').getByRole('button', { name: 'Jump to a month' });
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	await toggle.click();
	await expect(toggle).toHaveAttribute('aria-expanded', 'true');
	const may = page.getByRole('navigation', { name: 'Jump to a month' }).getByRole('button', { name: /^May 2024/ });
	await expect(may).toBeInViewport();
	await may.click();
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	await expect(page.locator('main').getByText('Anyone up for a game tonight?').first()).toBeInViewport();
});

test('on Search the refine facets open from Refine', async ({ page }) => {
	await page.goto('/search?q=hello', { waitUntil: 'networkidle' });
	await page.locator('main').getByRole('button', { name: 'Refine' }).click();
	await expect(page.getByRole('button', { name: '#general: 1 result' })).toBeInViewport();
});

test('on the Media screen the channel filter is in reach and filters', async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	const channel = page.locator('main').getByLabel('Channel');
	await expect(channel).toBeInViewport();
	await channel.selectOption({ label: '#art' });
	await expect(page).toHaveURL(/[?&]channel=900000000000000022/);
});
