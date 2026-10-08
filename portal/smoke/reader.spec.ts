// Browse's reader opens at a channel's newest messages and pages back in time,
// adding older messages above without moving what is in view (ADR 0003, #56, #60).
//
// The smoke archive's channels fit in one page, so the paging tests narrow every
// messages request to PAGE messages; general's six then take three pages.
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';
import { narrowPages, said, topOf } from './reader.ts';

// Ids and text from tests/smoke_archive.py.
const GENERAL_ID = '900000000000000020';
const PAGE = 2;

interface Reader {
	/** The route as SvelteKit names it under src/routes. */
	route: string;
	/** The URL that opens the reader on a channel. */
	url: (channelId: string) => string;
}

const READERS: Reader[] = [{ route: '/browse/[channel]', url: (id) => `/browse/${id}` }];

for (const reader of READERS) {
	const annotation = { type: ROUTE_ANNOTATION, description: reader.route };

	test(`${reader.route} opens at the newest message`, { annotation }, async ({ page }) => {
		// Short enough that general's six messages overflow the reader.
		await page.setViewportSize({ width: 1280, height: 400 });
		await page.goto(reader.url(GENERAL_ID), { waitUntil: 'networkidle' });
		const main = page.locator('main');
		await expect(said(main, 'The hello world of June.')).toBeInViewport();
		const first = said(main, 'Welcome to the smoke test guild!');
		await expect(first).not.toBeInViewport();
		// Oldest at the top, newest at the bottom.
		expect(await topOf(page, 'Welcome to the smoke test guild!')).toBeLessThan(
			await topOf(page, 'The hello world of June.')
		);
	});

	// A tall window holds general's first page with room to spare, so the feed sits at
	// the bottom; a short one overflows from the first page on.
	for (const height of [1000, 300]) {
		test(
			`${reader.route} loads older messages above the one in view (${height}px tall)`,
			{ annotation },
			async ({ page }) => {
				await page.setViewportSize({ width: 1280, height });
				await narrowPages(page, PAGE);
				await page.goto(reader.url(GENERAL_ID), { waitUntil: 'networkidle' });
				const main = page.locator('main');
				const newest = said(main, 'The hello world of June.');
				await expect(newest).toBeInViewport();
				await expect(said(main, 'Count me in.')).toHaveCount(0);

				const loadOlder = main.getByRole('button', { name: 'Load older messages' });
				for (const [inView, older] of [
					['June already?', 'Count me in.'],
					['Anyone up for a game tonight?', 'Thanks, glad to be here.']
				]) {
					await loadOlder.scrollIntoViewIfNeeded();
					await expect(said(main, inView)).toBeInViewport();
					const before = await topOf(page, inView);
					await loadOlder.click();
					await expect(said(main, older)).toBeAttached();
					await page.waitForLoadState('networkidle');
					expect(Math.abs((await topOf(page, inView)) - before)).toBeLessThanOrEqual(3);
					expect(await topOf(page, older)).toBeLessThan(before);
				}

				// general's first message is loaded, so there is nothing older to ask for.
				await expect(said(main, 'Welcome to the smoke test guild!')).toBeAttached();
				await expect(loadOlder).toHaveCount(0);
			}
		);
	}
}
