// The ⌘K command palette (#59): it opens from every screen, jumps to a destination, a
// channel of the selected guild or a person, hands a query to Search, re-ranks without
// moving, and is a labelled modal dialog that keeps focus and gives it back.
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures.ts';

// Ids and names from tests/smoke_archive.py.
const RANDOM_ID = '900000000000000021';
const ALICE_ID = '900000000000000100';
const NIGHT_GUILD_ID = '900000000000000002';

/** Every screen the palette must open from. */
const SCREENS = [
	'/',
	'/browse',
	'/browse/900000000000000020',
	'/search?q=hello',
	'/media',
	'/people',
	`/people/${ALICE_ID}`,
	'/archive'
];

const palette = (page: Page) => page.getByRole('dialog', { name: 'Command palette' });
const field = (page: Page) => palette(page).getByRole('combobox');
const options = (page: Page) => palette(page).getByRole('option');

async function openPalette(page: Page) {
	await page.keyboard.press('ControlOrMeta+k');
	await expect(palette(page)).toBeVisible();
	await expect(field(page)).toBeFocused();
}

for (const url of SCREENS) {
	test(`Ctrl+K opens the palette on ${url}, and Esc closes it`, async ({ page }) => {
		await page.goto(url, { waitUntil: 'networkidle' });
		// Browse's index opens its most active channel.
		const opened = page.url();
		await openPalette(page);
		await page.keyboard.press('Escape');
		await expect(palette(page)).toBeHidden();
		await expect(page).toHaveURL(opened);
	});
}

test('typing a channel name and Enter opens that channel', async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	await openPalette(page);
	await field(page).fill('random');
	const active = palette(page).getByRole('option', { selected: true });
	await expect(active).toContainText('random');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(`/browse/${RANDOM_ID}`);
	await expect(palette(page)).toBeHidden();
	await expect(page.locator('main h1').first()).toContainText('random');
});

test('Enter typed before the channels are read still opens the channel', async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	await page.route('**/api/guilds/900000000000000001', async (route) => {
		await new Promise((resolve) => setTimeout(resolve, 600));
		await route.continue();
	});
	await openPalette(page);
	await page.keyboard.type('random');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(`/browse/${RANDOM_ID}`);
});

test('Esc closes the palette and returns focus to what had it', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const people = page.getByRole('navigation', { name: 'Destinations' }).getByRole('link', { name: 'People' });
	await people.focus();
	await openPalette(page);
	await page.keyboard.press('Escape');
	await expect(palette(page)).toBeHidden();
	await expect(people).toBeFocused();
	await expect(page).toHaveURL('/');
});

test('the palette is a labelled modal dialog that keeps focus inside it', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await openPalette(page);
	const dialog = palette(page);
	expect(await dialog.evaluate((el) => el.tagName === 'DIALOG' && (el as HTMLDialogElement).matches(':modal'))).toBe(
		true
	);
	await expect(field(page)).toHaveAttribute('aria-controls', 'palette-results');
	await expect(palette(page).getByRole('listbox', { name: 'Results' })).toBeVisible();
	const activeId = await field(page).getAttribute('aria-activedescendant');
	await expect(page.locator(`#${activeId}`)).toHaveAttribute('aria-selected', 'true');

	for (const key of ['Tab', 'Tab', 'Shift+Tab', 'Shift+Tab', 'Shift+Tab']) {
		await page.keyboard.press(key);
		expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
	}
	// A click on the backdrop closes it.
	await page.mouse.click(5, 5);
	await expect(dialog).toBeHidden();
});

test('arrows move between results, and the clicked one opens', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await openPalette(page);
	await expect(options(page).first()).toHaveText(/^\s*Overview/);
	await expect(options(page).first()).toHaveAttribute('aria-selected', 'true');
	await page.keyboard.press('ArrowDown');
	await expect(options(page).nth(1)).toHaveAttribute('aria-selected', 'true');
	await page.keyboard.press('ArrowUp');
	await page.keyboard.press('ArrowUp');
	await expect(options(page).last()).toHaveAttribute('aria-selected', 'true');

	await options(page).filter({ hasText: 'Media' }).click();
	await expect(page).toHaveURL('/media');
});

test('a person opens their profile', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await openPalette(page);
	await field(page).fill('alice');
	const alice = palette(page).getByRole('option', { name: /^Alice/ });
	await expect(alice).toBeVisible();
	await expect(palette(page).getByRole('option', { selected: true })).toHaveText(/^\s*Alice/);
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(`/people/${ALICE_ID}`);
});

test('a destination opens from its name', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await openPalette(page);
	await field(page).fill('peo');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL('/people');
});

test('"Search messages for" hands the query to Search', async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	await openPalette(page);
	await field(page).fill('hello');
	const search = palette(page).getByRole('option', { name: 'Search messages for “hello”' });
	await expect(search).toBeVisible();
	await search.click();
	await expect(page).toHaveURL('/search?q=hello');
	await expect(page.locator('main').getByRole('combobox', { name: 'Search query' })).toHaveValue('hello');
	await expect(page.locator('main').getByText('The hello world of June.')).toBeVisible();
});

test('a query nothing else matches searches messages on Enter', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await openPalette(page);
	await field(page).fill('zzqx');
	await expect(options(page)).toHaveCount(1);
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL('/search?q=zzqx');
});

test("the palette lists the selected guild's channels and people", async ({ page }) => {
	await page.goto(`/?guild=${NIGHT_GUILD_ID}`, { waitUntil: 'networkidle' });
	await openPalette(page);
	const channels = palette(page).getByRole('group', { name: 'Channels' });
	await expect(channels.getByRole('option', { name: /^lounge/ })).toBeVisible();
	await expect(channels.getByRole('option', { name: /^general/ })).toHaveCount(0);
	await expect(palette(page).getByRole('group', { name: 'People' }).getByRole('option', { name: /^Carol/ })).toBeVisible();

	await field(page).fill('lounge');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(new RegExp(`/browse/900000000000000031\\?guild=${NIGHT_GUILD_ID}$`));
});

test('the palette reads what it lists when it first opens, once', async ({ page }) => {
	const calls: string[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (url.pathname.startsWith('/api/')) calls.push(url.pathname + url.search);
	});
	await page.goto('/archive', { waitUntil: 'networkidle' });
	const before = calls.length;
	await openPalette(page);
	await expect(palette(page).getByRole('group', { name: 'Channels' })).toBeVisible();
	await page.keyboard.press('Escape');
	await openPalette(page);
	await expect(palette(page).getByRole('group', { name: 'Channels' })).toBeVisible();
	await page.waitForLoadState('networkidle');
	const opened = calls.slice(before);
	expect(opened.sort()).toEqual(['/api/guilds/900000000000000001', '/api/guilds/900000000000000001/users?limit=6']);
});

test('results re-rank as the query changes without moving the palette', async ({ page }) => {
	await page.setViewportSize({ width: 1440, height: 900 });
	await page.goto('/', { waitUntil: 'networkidle' });
	await openPalette(page);
	await expect(palette(page).getByRole('group', { name: 'People' })).toBeVisible();
	const results = palette(page).getByRole('listbox');
	const boxes = async () => [await palette(page).boundingBox(), await results.boundingBox()];
	// Measured once it has finished scaling in.
	await palette(page).evaluate((el) => Promise.all(el.getAnimations().map((a) => a.finished)));
	const first = await boxes();

	for (const q of ['a', 'ar', 'art', 'lurker 00', 'zzqx', '']) {
		await field(page).fill(q);
		await page.waitForTimeout(300);
		expect(await boxes()).toEqual(first);
	}
	await field(page).fill('art');
	await expect(options(page).first()).toHaveText(/^\s*art\b/);
	await expect(options(page).first()).toHaveAttribute('aria-selected', 'true');
});

/** The keyframes the palette entered with, and its backdrop's filter. */
async function motion(page: Page) {
	// Record each animation on the dialog as it starts; it is over by the time it is visible.
	await page.evaluate(() => {
		const seen: Keyframe[] = [];
		(window as unknown as { seen: Keyframe[] }).seen = seen;
		document.addEventListener('animationstart', (event) => {
			const target = event.target as Element;
			if (target.id !== 'command-palette' || event.pseudoElement) return;
			for (const animation of target.getAnimations()) {
				seen.push(...(animation.effect as KeyframeEffect).getKeyframes());
			}
		});
	});
	await openPalette(page);
	return palette(page).evaluate((el) => {
		const seen = (window as unknown as { seen: ComputedKeyframe[] }).seen;
		const meta = ['offset', 'easing', 'composite', 'computedOffset'];
		return {
			backdrop: getComputedStyle(el, '::backdrop').backdropFilter,
			keyframes: seen.flatMap((k) => Object.keys(k).filter((p) => !meta.includes(p))),
			transform: seen.map((k) => k.transform)
		};
	});
}

test('the palette scales in from 0.98 over an 8px backdrop blur', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const { backdrop, keyframes, transform } = await motion(page);
	expect(backdrop).toBe('blur(8px)');
	expect(keyframes).toContain('opacity');
	expect(transform).toContain('scale(0.98)');
});

test('with reduced motion, the palette only fades in', async ({ page }) => {
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await page.goto('/', { waitUntil: 'networkidle' });
	const { backdrop, keyframes } = await motion(page);
	expect(backdrop).toBe('blur(8px)');
	expect([...new Set(keyframes)]).toEqual(['opacity']);
});
