// The keyboard map (#59): ⌘1–5 go to the five destinations and `?` shows the map from
// every screen, `/` searches in the current view, Esc clears a field, and keys without
// a modifier leave a field being typed in alone.
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures.ts';

// Ids from tests/smoke_archive.py.
const ALICE_ID = '900000000000000100';

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

/** The five destinations' URLs, in ⌘1–5's order. Browse's index opens its most active channel. */
const DESTINATIONS = [/\/$/, /\/browse\/\d+$/, /\/media$/, /\/search$/, /\/people$/];

const keymap = (page: Page) => page.getByRole('dialog', { name: 'Keyboard shortcuts' });

SCREENS.forEach((url, i) => {
	test(`? shows the keyboard map and Ctrl+1–5 go to a destination from ${url}`, async ({ page }) => {
		await page.goto(url, { waitUntil: 'networkidle' });
		await page.keyboard.press('?');
		await expect(keymap(page)).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(keymap(page)).toBeHidden();

		// A different destination from each screen, so each digit is pressed at least once.
		const n = (i % 5) + 1;
		await page.keyboard.press(`ControlOrMeta+${n}`);
		await expect(page).toHaveURL(DESTINATIONS[n - 1]);
		await expect(
			page.getByRole('navigation', { name: 'Destinations' }).getByRole('link').nth(n - 1)
		).toHaveAttribute('aria-current', 'page');
	});
});

test('Ctrl+1–5 go to the five destinations in order', async ({ page }) => {
	await page.goto('/archive', { waitUntil: 'networkidle' });
	for (const [i, url] of DESTINATIONS.entries()) {
		await page.keyboard.press(`ControlOrMeta+${i + 1}`);
		await expect(page).toHaveURL(url);
	}
});

test('the keyboard map lists every shortcut, as keys, and gives focus back', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const button = page.getByRole('button', { name: 'Keyboard shortcuts (?)' });
	await button.click();
	const map = keymap(page);
	await expect(map).toBeVisible();
	for (const does of [
		'Open the command palette',
		'Go to Overview',
		'Go to Browse',
		'Go to Media',
		'Go to Search',
		'Go to People',
		'Collapse or expand the sidebar',
		'Search in this view',
		'Close or clear',
		'Show this map'
	]) {
		await expect(map.getByText(does, { exact: true })).toBeVisible();
	}
	const palette = map.locator('.row', { hasText: 'Open the command palette' }).locator('kbd');
	await expect(palette).toHaveText(['Ctrl', 'K']);
	// The arrows are drawn as icons, not glyphs.
	await expect(map.locator('.row', { hasText: 'Move between results' }).locator('kbd svg')).toHaveCount(2);

	// Focus stays in the map, and Esc gives it back to the button.
	for (let i = 0; i < 3; i++) {
		await page.keyboard.press('Tab');
		expect(await map.evaluate((el) => el.contains(document.activeElement))).toBe(true);
	}
	await page.keyboard.press('Escape');
	await expect(map).toBeHidden();
	await expect(button).toBeFocused();
});

test("/ focuses the view's own search field", async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	await page.keyboard.press('/');
	const field = page.locator('main').getByRole('searchbox');
	await expect(field).toBeFocused();
	await expect(field).toHaveValue('');
	await expect(page).toHaveURL('/people');

	await page.goto('/search?q=hello', { waitUntil: 'networkidle' });
	await page.keyboard.press('/');
	await expect(page.locator('main').getByRole('combobox', { name: 'Search query' })).toBeFocused();
});

test('/ opens Search where the view has no search field', async ({ page }) => {
	await page.goto('/archive', { waitUntil: 'networkidle' });
	await page.keyboard.press('/');
	await expect(page).toHaveURL('/search');
	await expect(page.locator('main').getByRole('combobox', { name: 'Search query' })).toBeFocused();
});

test("? lists Browse's own keys on Browse, and only there", async ({ page }) => {
	await page.goto('/browse/900000000000000020', { waitUntil: 'networkidle' });
	await page.keyboard.press('?');
	const browse = keymap(page).locator('section', { has: page.getByRole('heading', { name: 'Browse' }) });
	await expect(browse.locator('dt')).toHaveText(['Next message', 'Previous message', 'Newest messages (G then L)']);
	await expect(browse.locator('.row', { hasText: 'Newest' }).locator('kbd')).toHaveText(['G', 'L']);
	await page.keyboard.press('Escape');

	await page.keyboard.press('ControlOrMeta+5');
	await expect(page).toHaveURL('/people');
	await page.keyboard.press('?');
	await expect(keymap(page).getByRole('heading', { name: 'Everywhere' })).toBeVisible();
	await expect(keymap(page).getByRole('heading', { name: 'Browse' })).toHaveCount(0);
});

test('keys without a modifier type into a field rather than act', async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	const field = page.locator('main').getByRole('searchbox');
	await field.click();
	await page.keyboard.type('a/b?');
	await expect(field).toHaveValue('a/b?');
	await expect(keymap(page)).toHaveCount(0);
	expect(new URL(page.url()).pathname).toBe('/people');
});

test('Esc clears a field, then leaves it', async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	const field = page.locator('main').getByRole('searchbox');
	await field.fill('ali');
	await page.keyboard.press('Escape');
	await expect(field).toHaveValue('');
	await expect(field).toBeFocused();
	await page.keyboard.press('Escape');
	await expect(field).not.toBeFocused();
});
