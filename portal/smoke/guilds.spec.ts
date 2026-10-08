// The selected guild (#58): every screen shows the guild the URL's `guild` names,
// switching guild re-scopes the screen you are on, and nothing reads the first guild
// when another is selected.
//
// The smoke archive holds two guilds that share nothing (tests/smoke_archive.py):
// "Smoke Test Guild", the first and the default, and "Night Owls".
import type { Locator, Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids and text from tests/smoke_archive.py.
const GUILD_ID = '900000000000000001';
const NIGHT_ID = '900000000000000002';
const GENERAL_ID = '900000000000000020';
const LOUNGE_ID = '900000000000000031';
const PHOTOS_ID = '900000000000000032';
const CAROL_ID = '900000000000000110';

/** Every /api request the page makes from now on, as "METHOD /path?query". */
function apiCalls(page: Page): string[] {
	const calls: string[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (url.pathname.startsWith('/api/')) calls.push(`${request.method()} ${url.pathname}${url.search}`);
	});
	return calls;
}

/** The calls that read the first guild: its own paths, or a read scoped to it. */
function firstGuildCalls(calls: string[]): string[] {
	return calls.filter((c) => c.includes(`/guilds/${GUILD_ID}`) || c.includes(`guild_id=${GUILD_ID}`));
}

/** Pick `name` in the sidebar's guild switcher. */
async function switchGuild(page: Page, name: string): Promise<void> {
	await page.getByRole('button', { name: /^Guild:/ }).click();
	await page.getByRole('listbox', { name: 'Guilds' }).getByRole('option', { name: new RegExp(name) }).click();
}

/** Go to a destination through the sidebar. */
async function open(page: Page, destination: string): Promise<void> {
	await page.getByRole('navigation', { name: 'Destinations' }).getByRole('link', { name: destination }).click();
}

function stat(main: Locator, label: string): Locator {
	return main.locator('.stat-card', { hasText: label }).locator('.stat-value');
}

test('switching guild re-scopes every destination, and the URL carries it through navigation and reload', async ({
	page
}) => {
	const calls = apiCalls(page);
	const main = page.locator('main');
	await page.goto('/', { waitUntil: 'networkidle' });
	await expect(stat(main, 'Messages')).toHaveText('135');

	await switchGuild(page, 'Night Owls');
	await expect(page).toHaveURL(`/?guild=${NIGHT_ID}`);
	await expect(page.getByRole('button', { name: 'Guild: Night Owls' })).toBeVisible();
	await expect(stat(main, 'Messages')).toHaveText('5');
	await expect(stat(main, 'Channels')).toHaveText('3');
	await expect(stat(main, 'Authors')).toHaveText('2');
	await expect(stat(main, 'Attachments')).toHaveText('1');

	// Browse opens Night Owls' most active channel.
	await open(page, 'Browse');
	await expect(page).toHaveURL(`/browse/${LOUNGE_ID}?guild=${NIGHT_ID}`);
	await expect(main.getByRole('heading', { name: 'lounge' })).toBeVisible();
	await expect(main.getByText('general', { exact: true })).toHaveCount(0);

	await open(page, 'Media');
	await expect(page).toHaveURL(`/media?guild=${NIGHT_ID}`);
	await expect(main.getByRole('img', { name: 'moonrise.png' })).toBeVisible();
	await expect(main.getByRole('img', { name: 'sketch.png' })).toHaveCount(0);

	await open(page, 'People');
	await expect(page).toHaveURL(`/people?guild=${NIGHT_ID}`);
	await expect(main.getByText('Carol', { exact: true })).toBeVisible();
	await expect(main.getByText('Alice', { exact: true })).toHaveCount(0);

	// The sidebar's search field searches the selected guild.
	await page.getByRole('searchbox', { name: 'Search messages' }).fill('game');
	await page.getByRole('searchbox', { name: 'Search messages' }).press('Enter');
	await expect(page).toHaveURL(`/search?q=game&guild=${NIGHT_ID}`);
	await expect(main.getByText('Game night is on Friday.')).toBeVisible();
	await expect(main.getByText('Anyone up for a game tonight?')).toHaveCount(0);

	await page.reload({ waitUntil: 'networkidle' });
	await expect(page.getByRole('button', { name: 'Guild: Night Owls' })).toBeVisible();
	await expect(main.getByText('Game night is on Friday.')).toBeVisible();
	await expect(main.getByText('Anyone up for a game tonight?')).toHaveCount(0);

	// The Overview's first visit read the first guild; nothing did once Night Owls was picked.
	const afterSwitch = calls.slice(calls.findIndex((c) => c.includes(`/guilds/${NIGHT_ID}`)));
	expect(firstGuildCalls(afterSwitch)).toEqual([]);
});

test('switching guild stays on the screen, and re-reads it once', async ({ page }) => {
	await page.goto('/people', { waitUntil: 'networkidle' });
	const calls = apiCalls(page);
	await switchGuild(page, 'Night Owls');
	await expect(page).toHaveURL(`/people?guild=${NIGHT_ID}`);
	await expect(page.locator('main').getByText('Carol', { exact: true })).toBeVisible();
	await page.waitForLoadState('networkidle');
	expect(calls).toEqual([`GET /api/guilds/${NIGHT_ID}/users?limit=50&sort=messages`]);
});

test("switching guild on a channel goes to Browse's index, as the channel is not in the other guild", async ({
	page
}) => {
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	await switchGuild(page, 'Night Owls');
	// Browse's index, which opens Night Owls' most active channel.
	await expect(page).toHaveURL(`/browse/${LOUNGE_ID}?guild=${NIGHT_ID}`);
	await expect(page.locator('main').getByRole('heading', { name: 'lounge' })).toBeVisible();
});

test("a screen's own links keep the selected guild", async ({ page }) => {
	await page.goto(`/browse/${LOUNGE_ID}?guild=${NIGHT_ID}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await main.getByRole('link', { name: /photos/ }).click();
	await expect(page).toHaveURL(`/browse/${PHOTOS_ID}?guild=${NIGHT_ID}`);
	await expect(main.getByText('Long exposure attempt')).toBeVisible();

	await main.getByRole('link', { name: /lounge/ }).click();
	await expect(page).toHaveURL(`/browse/${LOUNGE_ID}?guild=${NIGHT_ID}`);
	await expect(main.getByText('Night owls unite.')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Guild: Night Owls' })).toBeVisible();
});

test('a channel link without a guild selects the guild that holds the channel', async ({ page }) => {
	await page.goto(`/browse/${LOUNGE_ID}`, { waitUntil: 'networkidle' });
	await expect(page).toHaveURL(`/browse/${LOUNGE_ID}?guild=${NIGHT_ID}`);
	await expect(page.getByRole('button', { name: 'Guild: Night Owls' })).toBeVisible();
	await expect(page.locator('main').getByRole('heading', { name: 'lounge' })).toBeVisible();
	await expect(page.locator('main').getByText('Night owls unite.')).toBeVisible();
});

interface Visit {
	route: string;
	url: string;
	/** Night Owls text the screen shows. */
	shows: (main: Locator) => Locator;
	/** Smoke Test Guild text it must not show. */
	hides: (main: Locator) => Locator;
}

const g = `guild=${NIGHT_ID}`;
const exact = { exact: true };

// Every route, opened with Night Owls selected.
const VISITS: Visit[] = [
	{
		route: '/',
		url: `/?${g}`,
		shows: (m) => m.getByText('Night Owls'),
		hides: (m) => m.getByText('Smoke Test Guild')
	},
	{
		route: '/browse',
		url: `/browse?${g}`,
		shows: (m) => m.getByText('Night owls unite.'),
		hides: (m) => m.getByText('general', exact)
	},
	{
		route: '/browse/[channel]',
		url: `/browse/${LOUNGE_ID}?${g}`,
		shows: (m) => m.getByText('Game night is on Friday.'),
		hides: (m) => m.getByText('general', exact)
	},
	{
		route: '/search',
		url: `/search?q=game&${g}`,
		shows: (m) => m.getByText('Game night is on Friday.'),
		hides: (m) => m.getByText('Anyone up for a game tonight?')
	},
	{
		route: '/media',
		url: `/media?${g}`,
		shows: (m) => m.getByRole('img', { name: 'moonrise.png' }),
		hides: (m) => m.getByRole('img', { name: 'sketch.png' })
	},
	{
		route: '/people',
		url: `/people?${g}`,
		shows: (m) => m.getByText('Carol', exact),
		hides: (m) => m.getByText('Alice', exact)
	},
	{
		route: '/people/[id]',
		url: `/people/${CAROL_ID}?${g}`,
		shows: (m) => m.getByText('#lounge', exact),
		hides: (m) => m.getByText('#general', exact)
	},
	{
		// The Archive screen starts a scrape of the selected guild by default.
		route: '/archive',
		url: `/archive?${g}`,
		shows: (m) => m.locator(`#guild-select:has(option[value="${NIGHT_ID}"]:checked)`),
		hides: (m) => m.locator(`#guild-select:has(option[value="${GUILD_ID}"]:checked)`)
	}
];

for (const visit of VISITS) {
	test(
		`${visit.route} shows only the selected guild`,
		{ annotation: { type: ROUTE_ANNOTATION, description: visit.route } },
		async ({ page }) => {
			const calls = apiCalls(page);
			await page.goto(visit.url, { waitUntil: 'networkidle' });
			const main = page.locator('main');
			await expect(visit.shows(main).first()).toBeVisible();
			await expect(visit.hides(main)).toHaveCount(0);
			await expect(page.getByRole('button', { name: 'Guild: Night Owls' })).toBeVisible();
			expect(firstGuildCalls(calls), `${visit.route} reads nothing of the first guild`).toEqual([]);
		}
	);
}
