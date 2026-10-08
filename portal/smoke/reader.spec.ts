// The channel readers open at a channel's newest messages and page back in time,
// adding older messages above without moving what is in view (ADR 0003, #56).
//
// The smoke archive's channels fit in one page, so the paging tests narrow every
// messages request to PAGE messages; general's six then take three pages.
import type { Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids and text from tests/smoke_archive.py.
const GENERAL_ID = '900000000000000020';
const PAGE = 2;

interface Reader {
	/** The route as SvelteKit names it under src/routes. */
	route: string;
	/** The URL that opens the reader on a channel. */
	url: (channelId: string) => string;
}

const READERS: Reader[] = [
	{ route: '/channel/[id]', url: (id) => `/channel/${id}` },
	{ route: '/timeline', url: (id) => `/timeline?channel=${id}` }
];

/** Answer every channel messages request with at most `limit` messages. */
async function narrowPages(page: Page, limit: number): Promise<void> {
	await page.route(
		(url) => url.pathname.startsWith('/api/channels/') && url.pathname.endsWith('/messages'),
		async (route) => {
			const url = new URL(route.request().url());
			url.searchParams.set('limit', String(limit));
			await route.continue({ url: url.href });
		}
	);
}

/** The top of the message whose text is `text`, in viewport pixels. */
async function topOf(page: Page, text: string): Promise<number> {
	const box = await page.locator('main').getByText(text, { exact: true }).boundingBox();
	expect(box, `${text} is laid out`).not.toBeNull();
	return box!.y;
}

for (const reader of READERS) {
	const annotation = { type: ROUTE_ANNOTATION, description: reader.route };

	test(`${reader.route} opens at the newest message`, { annotation }, async ({ page }) => {
		// Short enough that general's six messages overflow the reader.
		await page.setViewportSize({ width: 1280, height: 540 });
		await page.goto(reader.url(GENERAL_ID), { waitUntil: 'networkidle' });
		const main = page.locator('main');
		await expect(main.getByText('The hello world of June.', { exact: true })).toBeInViewport();
		const first = main.getByText('Welcome to the smoke test guild!', { exact: true });
		await expect(first).not.toBeInViewport();
		// Oldest at the top, newest at the bottom.
		expect(await topOf(page, 'Welcome to the smoke test guild!')).toBeLessThan(
			await topOf(page, 'The hello world of June.')
		);
	});

	// A tall window holds general's first page with room to spare, so the feed sits at
	// the bottom; a short one overflows from the first page on.
	for (const height of [1000, 540]) {
		test(
			`${reader.route} loads older messages above the one in view (${height}px tall)`,
			{ annotation },
			async ({ page }) => {
				await page.setViewportSize({ width: 1280, height });
				await narrowPages(page, PAGE);
				await page.goto(reader.url(GENERAL_ID), { waitUntil: 'networkidle' });
				const main = page.locator('main');
				const newest = main.getByText('The hello world of June.', { exact: true });
				await expect(newest).toBeInViewport();
				await expect(main.getByText('Count me in.', { exact: true })).toHaveCount(0);

				const loadOlder = main.getByRole('button', { name: 'Load older messages' });
				for (const [inView, older] of [
					['June already?', 'Count me in.'],
					['Anyone up for a game tonight?', 'Thanks, glad to be here.']
				]) {
					await loadOlder.scrollIntoViewIfNeeded();
					await expect(main.getByText(inView, { exact: true })).toBeInViewport();
					const before = await topOf(page, inView);
					await loadOlder.click();
					await expect(main.getByText(older, { exact: true })).toBeAttached();
					await page.waitForLoadState('networkidle');
					expect(Math.abs((await topOf(page, inView)) - before)).toBeLessThanOrEqual(3);
					expect(await topOf(page, older)).toBeLessThan(before);
				}

				// general's first message is loaded, so there is nothing older to ask for.
				await expect(main.getByText('Welcome to the smoke test guild!', { exact: true })).toBeAttached();
				await expect(loadOlder).toHaveCount(0);
			}
		);
	}
}
