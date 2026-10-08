// Every portal route opens over the smoke archive without errors and shows content.
//
// Later tickets add their own scenarios beside this file; a new route adds a row to
// ROUTES, which the last test checks against the routes in src/routes.
import { readdirSync } from 'node:fs';
import { dirname, join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids and text from tests/smoke_archive.py.
const ART_ID = '900000000000000022';
const ALICE_ID = '900000000000000100';

interface RouteVisit {
	/** The route as SvelteKit names it under src/routes. */
	route: string;
	/** The URL the test opens. */
	url: string;
	/** Text from the smoke archive the route must show in its main region. */
	shows: string;
	/** What the test does on the page after it loads, for routes that load more on demand. */
	act?: (page: Page) => Promise<void>;
}

const ROUTES: RouteVisit[] = [
	{ route: '/', url: '/', shows: 'Smoke Test Guild' },
	{ route: '/channels', url: '/channels', shows: 'general' },
	{ route: '/channel/[id]', url: `/channel/${ART_ID}`, shows: 'My first sketch' },
	{ route: '/channel/[id]/gallery', url: `/channel/${ART_ID}/gallery`, shows: 'art' },
	{ route: '/timeline', url: '/timeline', shows: 'Welcome to the smoke test guild!' },
	{ route: '/search', url: '/search?q=hello', shows: 'The hello world of June.' },
	{ route: '/gallery', url: '/gallery', shows: 'art' },
	{ route: '/users', url: '/users', shows: 'Alice' },
	{
		route: '/users/[id]',
		url: `/users/${ALICE_ID}`,
		shows: 'Alice',
		act: async (page) => {
			await page.getByRole('button', { name: 'Load Messages' }).first().click();
			await expect(page.getByRole('button', { name: 'Loaded' }).first()).toBeVisible();
		}
	},
	{ route: '/control', url: '/control', shows: '.smoke-archive/attachments' }
];

for (const visit of ROUTES) {
	test(
		`${visit.route} loads without errors`,
		{ annotation: { type: ROUTE_ANNOTATION, description: visit.route } },
		async ({ page }) => {
			await page.goto(visit.url, { waitUntil: 'networkidle' });
			const main = page.locator('main');
			await expect(main.getByText(visit.shows, { exact: false }).first()).toBeVisible();
			expect((await main.innerText()).trim()).not.toBe('');
			if (visit.act) {
				await visit.act(page);
				await page.waitForLoadState('networkidle');
			}
		}
	);
}

test('every route in src/routes has a smoke visit', () => {
	const routesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'routes');
	const pages = readdirSync(routesDir, { recursive: true, encoding: 'utf8' })
		.filter((file) => file.endsWith('+page.svelte'))
		.map((file) => '/' + dirname(file).split(sep).filter((p) => p !== '.').join('/'))
		.sort();
	expect(ROUTES.map((visit) => visit.route).sort()).toEqual(pages);
});
