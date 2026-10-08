// Search (#64): filter chips written into the query (`in:`, `from:`, `has:`, `after:`,
// `before:`), highlighted snippets, "Open in context" into Browse, a refine rail whose
// facets add chips, a sort, and all of it in the URL.
import type { Locator, Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids and text from tests/smoke_archive.py.
const GENERAL_ID = '900000000000000020';
/** "The hello world of June.", general's newest. */
const HELLO_ID = '900000000000001009';
const ZARA_LINK = 'Zara checks in, 2 of 3: https://example.com/zara';
const LURKER_LINK = 'Lurker 101 says hi, notes at https://example.com/lurk';
/** The messages carrying an image, newest first. */
const WITH_IMAGES = [
	'Last message in the archive.',
	'Another drawing',
	'Here is mine, plus the notes',
	'My first sketch',
	'Random thought: wumpus is the best mascot.'
];

const annotation = { type: ROUTE_ANNOTATION, description: '/search' };

function field(page: Page): Locator {
	return page.getByRole('combobox', { name: 'Search query' });
}

function rows(page: Page): Locator {
	return page.locator('main').getByRole('list', { name: 'Results' }).locator('> li');
}

/** The results' snippets, in order. */
function snippets(page: Page): Locator {
	return rows(page).locator('.snippet');
}

function chip(page: Page, text: string): Locator {
	return page.locator('main').getByRole('button', { name: `Remove ${text}` });
}

/** The chips in the query bar, as `kind:value`. */
async function chips(page: Page): Promise<string[]> {
	const texts = await page.locator('main .query-bar .chip').allInnerTexts();
	return texts.map((t) => t.replace(/\s+/g, ''));
}

function q(page: Page): string | null {
	return new URL(page.url()).searchParams.get('q');
}

function rail(page: Page): Locator {
	return page.getByRole('complementary', { name: 'Refine' });
}

test('typing from: and has:link restricts the results and shows both chips', { annotation }, async ({ page }) => {
	await page.goto('/search', { waitUntil: 'networkidle' });
	await expect(page.locator('main')).toContainText('Search the archive');
	await expect(page.locator('main')).not.toContainText('coming soon');

	await field(page).fill('from:zara has:link');
	await field(page).press('Enter');
	await expect.poll(() => q(page)).toBe('from:zara has:link');
	await expect(snippets(page)).toHaveText([ZARA_LINK]);
	await expect(page.locator('main .result-count')).toHaveText('1 result');
	expect(await chips(page)).toEqual(['from:zara', 'has:link']);
	await expect(field(page)).toHaveValue('');

	// Removing a chip widens the results: every link, then all of Zara's messages.
	await chip(page, 'from:zara').click();
	await expect.poll(() => q(page)).toBe('has:link');
	await expect(snippets(page)).toHaveText([ZARA_LINK, LURKER_LINK]);
	expect(await chips(page)).toEqual(['has:link']);

	await page.goBack();
	await expect.poll(() => q(page)).toBe('from:zara has:link');
	await expect(snippets(page)).toHaveText([ZARA_LINK]);
	await chip(page, 'has:link').click();
	await expect(snippets(page)).toHaveText([
		'Zara checks in, 3 of 3.',
		ZARA_LINK,
		'Zara checks in, 1 of 3.'
	]);
});

test('typing from: offers the authors whose names match', { annotation }, async ({ page }) => {
	await page.goto('/search', { waitUntil: 'networkidle' });
	await field(page).pressSequentially('example from:za');
	const option = page.getByRole('option', { name: /Zara/ });
	await expect(option).toBeVisible();
	await expect(page.getByRole('option')).toHaveCount(1);
	await field(page).press('ArrowDown');
	await field(page).press('Enter');
	await expect.poll(() => q(page)).toBe('from:zara example');
	expect(await chips(page)).toEqual(['from:zara']);
	await expect(snippets(page)).toHaveText([ZARA_LINK]);
	await expect(field(page)).toHaveValue('example');
});

test('has:image keeps only the messages that carry an image', { annotation }, async ({ page }) => {
	const read = page.waitForRequest((r) => new URL(r.url()).pathname === '/api/search');
	await page.goto('/search?q=has:image', { waitUntil: 'networkidle' });
	expect(new URL((await read).url()).searchParams.get('has')).toBe('image');
	await expect(snippets(page)).toHaveText(WITH_IMAGES);
	for (const row of await rows(page).all()) {
		await expect(row.locator('.attachments')).toContainText(/\d+ images?/);
	}
});

test('date chips bound the results', { annotation }, async ({ page }) => {
	await page.goto('/search?q=has:image after:2024-06-01', { waitUntil: 'networkidle' });
	await expect(snippets(page)).toHaveText(WITH_IMAGES.slice(0, 2));
	expect(await chips(page)).toEqual(['has:image', 'after:2024-06-01']);

	await field(page).fill('before:2024-06-01');
	await field(page).press('Enter');
	await expect.poll(() => q(page)).toBe('has:image after:2024-06-01 before:2024-06-01');
	await expect(page.locator('main')).toContainText('No messages match');

	await chip(page, 'after:2024-06-01').click();
	await expect(snippets(page)).toHaveText(WITH_IMAGES.slice(2));
});

test('the highlight marks every occurrence and shows markup as text', { annotation }, async ({ page }) => {
	await page.goto('/search?q=echo', { waitUntil: 'networkidle' });
	const snippet = snippets(page);
	await expect(snippet).toHaveText(['Lurker 102 shouts echo <b>echo</b> & echo!']);
	await expect(snippet.locator('mark')).toHaveText(['echo', 'echo', 'echo']);
	await expect(snippet.locator('b')).toHaveCount(0);
});

test('Open in context lands on the message in Browse', { annotation }, async ({ page }) => {
	await page.goto('/search?q=hello', { waitUntil: 'networkidle' });
	const row = rows(page).first();
	await expect(row.locator('mark')).toHaveText(['hello']);
	const open = row.getByRole('link', { name: 'Open in context' });
	await expect(open).toHaveCSS('opacity', '0');
	await row.hover();
	await expect(open).toHaveCSS('opacity', '1');
	await open.click();
	await expect(page).toHaveURL(`/browse/${GENERAL_ID}?message=${HELLO_ID}`);
	const card = page.locator(`main [data-message-id="${HELLO_ID}"]`);
	await expect(card).toHaveAttribute('aria-current', 'true');
	await expect(card).toBeInViewport();
});

test('facets add chips, and reload and back keep everything', { annotation }, async ({ page }) => {
	await page.goto('/search?q=has:image', { waitUntil: 'networkidle' });
	await expect(rail(page).getByRole('button', { name: /^#/ })).toHaveText([/art\s*3/, /random\s*2/]);

	await rail(page).getByRole('button', { name: '#art: 3 results' }).click();
	await expect.poll(() => q(page)).toBe('in:art has:image');
	await expect(snippets(page)).toHaveText(WITH_IMAGES.slice(1, 4));

	await rail(page).getByRole('button', { name: 'Alice: 2 results' }).click();
	await expect.poll(() => q(page)).toBe('in:art from:alice has:image');
	await expect(snippets(page)).toHaveText(['Another drawing', 'My first sketch']);

	await rail(page).getByRole('button', { name: 'Jun 2024: 1 result' }).click();
	await expect.poll(() => q(page)).toBe('in:art from:alice has:image after:2024-06-01 before:2024-07-01');
	await expect(snippets(page)).toHaveText(['Another drawing']);
	await expect(rail(page).getByRole('button', { name: 'Jun 2024: 1 result' })).toHaveAttribute('aria-pressed', 'true');

	// Back to two chips, sorted oldest first, then reloaded.
	await page.goBack();
	await expect.poll(() => q(page)).toBe('in:art from:alice has:image');
	await page.getByRole('radio', { name: 'Oldest' }).click();
	await expect(snippets(page)).toHaveText(['My first sketch', 'Another drawing']);
	await page.reload({ waitUntil: 'networkidle' });
	expect(new URL(page.url()).searchParams.get('sort')).toBe('oldest');
	expect(await chips(page)).toEqual(['in:art', 'from:alice', 'has:image']);
	await expect(snippets(page)).toHaveText(['My first sketch', 'Another drawing']);
	await expect(page.getByRole('radio', { name: 'Oldest' })).toHaveAttribute('aria-checked', 'true');

	// A facet in force takes its chip off again.
	await rail(page).getByRole('button', { name: '#art: 2 results' }).click();
	await expect.poll(() => q(page)).toBe('from:alice has:image');
});

test('Load more pages on in the sort, and the count is the total', { annotation }, async ({ page }) => {
	await page.goto('/search?q=says hi', { waitUntil: 'networkidle' });
	// Every lurker but 102, whose message says something else.
	await expect(page.locator('main .result-count')).toHaveText('117 results');
	await expect(rows(page)).toHaveCount(50);
	await page.getByRole('button', { name: 'Load more results' }).click();
	await expect(rows(page)).toHaveCount(100);
	await page.getByRole('button', { name: 'Load more results' }).click();
	await expect(rows(page)).toHaveCount(117);
	await expect(page.getByRole('button', { name: 'Load more results' })).toHaveCount(0);
	await expect(snippets(page).last()).toHaveText(/^Lurker 001 says /);
});

test('a filter naming nothing in the guild says so', { annotation }, async ({ page }) => {
	await page.goto('/search?q=in:nowhere hello', { waitUntil: 'networkidle' });
	await expect(page.locator('main')).toContainText('No channel is named #nowhere in Smoke Test Guild.');
	await page.getByRole('button', { name: 'Clear search' }).first().click();
	await expect.poll(() => q(page)).toBeNull();
	await expect(page.locator('main')).toContainText('Search the archive');
});

test('on a phone, the refine rail opens from the result bar', { annotation }, async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto('/search?q=has:image', { waitUntil: 'networkidle' });
	await expect(rail(page)).toBeHidden();
	await page.getByRole('button', { name: 'Refine' }).click();
	await expect(rail(page)).toBeVisible();
	const main = page.locator('main');
	expect(await main.evaluate((m) => m.scrollWidth <= m.clientWidth)).toBe(true);
	// Without hover, "Open in context" is always shown.
	await expect(rows(page).first().getByRole('link', { name: 'Open in context' })).toBeVisible();
});
