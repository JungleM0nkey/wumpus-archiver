// Every portal route opens over the smoke archive without errors, shows content and
// issues each of its API calls once.
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
	{ route: '/people', url: '/people', shows: 'Alice' },
	{ route: '/people/[id]', url: `/people/${ALICE_ID}`, shows: 'Another drawing' },
	{ route: '/archive', url: '/archive', shows: '.smoke-archive/attachments' }
];

for (const visit of ROUTES) {
	test(
		`${visit.route} loads without errors`,
		{ annotation: { type: ROUTE_ANNOTATION, description: visit.route } },
		async ({ page }) => {
			const apiCalls: string[] = [];
			page.on('request', (request) => {
				const url = new URL(request.url());
				if (url.pathname.startsWith('/api/')) {
					apiCalls.push(`${request.method()} ${url.pathname}${url.search}`);
				}
			});
			await page.goto(visit.url, { waitUntil: 'networkidle' });
			const main = page.locator('main');
			await expect(main.getByText(visit.shows, { exact: false }).first()).toBeVisible();
			expect((await main.innerText()).trim()).not.toBe('');
			if (visit.act) {
				await visit.act(page);
				await page.waitForLoadState('networkidle');
			}
			expect(apiCalls.length, 'the route calls the API').toBeGreaterThan(0);
			const repeated = apiCalls.filter((call, i) => apiCalls.indexOf(call) !== i);
			expect(repeated, `${visit.route} issues each API call once`).toEqual([]);
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
