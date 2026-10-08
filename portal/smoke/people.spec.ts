// The People screen (#65): the selected guild's authors as a sortable, searchable table
// whose ranks follow the sort, 1..N however many pages are loaded; the old /users
// routes redirect to it.
import type { Locator, Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids and names from tests/smoke_archive.py: 122 authors in the first guild, whom the
// People screen loads 50 at a time. Zara (3 messages) and "aaron" (2) sort apart: by
// messages they follow Alice and Bob, by name "aaron" is first and Zara last.
const AUTHORS = 122;
const ALICE_ID = '900000000000000100';
const NIGHT_ID = '900000000000000002';
const CAROL_ID = '900000000000000110';

const people = { annotation: { type: ROUTE_ANNOTATION, description: '/people' } };

function table(page: Page): Locator {
	return page.getByRole('table');
}

/** The rows' cells in `column` (0-based), as shown. */
async function column(page: Page, index: number): Promise<string[]> {
	return table(page)
		.locator('tbody tr')
		.evaluateAll((rows, i) => rows.map((row) => (row.children[i] as HTMLElement).innerText.trim()), index);
}

const RANK = 0;
const PERSON = 1;
const SHARE = 2;
const MESSAGES = 3;
const ACTIVE = 4;

/** The rows' shown names, without their handles. */
async function names(page: Page): Promise<string[]> {
	return table(page).locator('tbody .name').allInnerTexts();
}

async function sortBy(page: Page, option: string): Promise<void> {
	await page.getByRole('radiogroup', { name: 'Sort by' }).getByRole('radio', { name: option }).click();
}

function ranks(count: number): string[] {
	return Array.from({ length: count }, (_, i) => String(i + 1));
}

test('People ranks run 1..N without gaps or repeats after two Load more clicks', people, async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	const rows = table(page).locator('tbody tr');
	await expect(rows).toHaveCount(50);

	const loadMore = page.getByRole('button', { name: /Load more/ });
	await loadMore.click();
	await expect(rows).toHaveCount(100);
	await loadMore.click();
	await expect(rows).toHaveCount(AUTHORS);
	await expect(loadMore).toHaveCount(0);

	expect(await column(page, RANK)).toEqual(ranks(AUTHORS));
});

test('People is a table of rank, person, share, messages and active range', people, async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	await expect(table(page).getByRole('columnheader')).toHaveText([
		'Rank#',
		'Person',
		'Share of messages',
		'Messages',
		'Active'
	]);
	await expect(table(page).getByRole('columnheader', { name: 'Messages', exact: true })).toHaveAttribute('aria-sort', 'descending');

	// Alice wrote 6 of the guild's 135 messages, from May 20 to Jun 22, 2024.
	const alice = table(page).getByRole('row').filter({ has: page.getByRole('link', { name: /Alice/ }) });
	const cells = alice.getByRole('cell');
	await expect(cells.nth(RANK)).toHaveText('1');
	await expect(cells.nth(PERSON).locator('.name')).toHaveText('Alice');
	await expect(cells.nth(PERSON).locator('.handle')).toHaveText('@alice');
	await expect(cells.nth(SHARE)).toHaveText('4.4%');
	await expect(cells.nth(MESSAGES)).toHaveText('6');
	await expect(cells.nth(ACTIVE)).toHaveText('May 20 – Jun 22, 2024');
	await expect(alice.getByRole('link')).toHaveAttribute('href', `/people/${ALICE_ID}`);
	await expect(page.locator('main .summary')).toHaveText(`${AUTHORS} people have posted in Smoke Test Guild`);
});

test('sorting by name and by messages reorders the table, and the ranks follow the sort', people, async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	const byMessages = ['Alice', 'Bob', 'Zara', 'aaron', 'Lurker 001'];
	await expect.poll(async () => (await names(page)).slice(0, 5)).toEqual(byMessages);
	const counts = (await column(page, MESSAGES)).map(Number);
	expect(counts).toEqual([...counts].sort((a, b) => b - a));
	expect(await column(page, RANK)).toEqual(ranks(50));

	const read = page.waitForRequest((r) => new URL(r.url()).pathname.endsWith('/users'));
	await sortBy(page, 'Name');
	expect(new URL((await read).url()).searchParams.get('sort')).toBe('name');
	await expect.poll(async () => (await names(page)).slice(0, 5)).toEqual([
		'aaron',
		'Alice',
		'Bob',
		'Lurker 001',
		'Lurker 002'
	]);
	const sorted = await names(page);
	expect(sorted).toEqual([...sorted].sort((a, b) => a.localeCompare(b, 'en', { sensitivity: 'base' })));
	expect(await column(page, RANK)).toEqual(ranks(50));
	await expect(page.getByRole('radio', { name: 'Name' })).toHaveAttribute('aria-checked', 'true');
	await expect(table(page).getByRole('columnheader', { name: 'Person' })).toHaveAttribute('aria-sort', 'ascending');

	// Zara sorts last by name, on the third page, and ranks last.
	const loadMore = page.getByRole('button', { name: /Load more/ });
	await loadMore.click();
	await loadMore.click();
	await expect(table(page).locator('tbody tr')).toHaveCount(AUTHORS);
	expect((await names(page)).at(-1)).toBe('Zara');
	expect(await column(page, RANK)).toEqual(ranks(AUTHORS));

	await sortBy(page, 'Messages');
	await expect(table(page).locator('tbody tr')).toHaveCount(50);
	await expect.poll(async () => (await names(page)).slice(0, 5)).toEqual(byMessages);
	expect(await column(page, RANK)).toEqual(ranks(50));
});

test('the sort is a radio group the arrow keys move through', people, async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	await page.getByRole('radio', { name: 'Messages' }).focus();
	await page.keyboard.press('ArrowRight');
	await expect(page.getByRole('radio', { name: 'Name' })).toBeFocused();
	await expect(page.getByRole('radio', { name: 'Name' })).toHaveAttribute('aria-checked', 'true');
	await expect.poll(async () => (await names(page))[0]).toBe('aaron');
	await page.keyboard.press('End');
	await expect(page.getByRole('radio', { name: 'Recently active' })).toHaveAttribute('aria-checked', 'true');
	// Bob wrote the guild's last message.
	await expect.poll(async () => (await names(page))[0]).toBe('Bob');
	await expect(table(page).getByRole('columnheader', { name: 'Active' })).toHaveAttribute('aria-sort', 'descending');
});

test('searching by name narrows the table and ranks the matches 1..N', people, async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	const field = page.getByRole('searchbox', { name: 'Search people by name' });
	await field.fill('lurker 11');
	await expect.poll(() => names(page)).toEqual(Array.from({ length: 9 }, (_, i) => `Lurker 11${i}`));
	expect(await column(page, RANK)).toEqual(ranks(9));
	await expect(page.locator('main .summary')).toHaveText('9 people match “lurker 11” in Smoke Test Guild');

	await field.fill('nobody at all');
	await expect(page.getByText('No one matches “nobody at all”.')).toBeVisible();

	await page.getByRole('button', { name: 'Clear search' }).click();
	await expect(table(page).locator('tbody tr')).toHaveCount(50);
	expect((await names(page)).slice(0, 2)).toEqual(['Alice', 'Bob']);
});

test('the person column links to the profile', people, async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	await table(page).getByRole('link', { name: /Alice/ }).click();
	await expect(page).toHaveURL(`/people/${ALICE_ID}`);
	await expect(page.locator('main h1')).toHaveText('Alice');
});

test('/users redirects to /people, keeping the guild', people, async ({ page }) => {
	await page.goto(`/users?guild=${NIGHT_ID}`, { waitUntil: 'networkidle' });
	await expect(page).toHaveURL(`/people?guild=${NIGHT_ID}`);
	await expect(page.locator('main h1')).toHaveText('People');
	expect(await names(page)).toEqual(['Carol', 'Dave']);
});

test(
	'/users/<id> redirects to /people/<id>, keeping the guild',
	{ annotation: { type: ROUTE_ANNOTATION, description: '/people/[id]' } },
	async ({ page }) => {
		await page.goto(`/users/${CAROL_ID}?guild=${NIGHT_ID}`, { waitUntil: 'networkidle' });
		await expect(page).toHaveURL(`/people/${CAROL_ID}?guild=${NIGHT_ID}`);
		await expect(page.locator('main h1')).toHaveText('Carol');
		await expect(page.getByRole('button', { name: 'Guild: Night Owls' })).toBeVisible();
	}
);

test('the sidebar marks People current on a profile', people, async ({ page }) => {
	await page.goto(`/people/${ALICE_ID}`, { waitUntil: 'networkidle' });
	const nav = page.getByRole('navigation', { name: 'Destinations' });
	await expect(nav.getByRole('link', { name: 'People' })).toHaveAttribute('aria-current', 'page');
	await expect(nav.getByRole('link', { name: 'People' })).toHaveAttribute('href', '/people');
});
