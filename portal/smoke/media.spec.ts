// The Media screen (#62): one justified, month-grouped grid fed by the gallery
// timeline replaces both galleries. Type, channel and sort are filters in the URL,
// month headers stick under the screen's header, tiles keep their natural shape, and
// videos and GIFs carry a badge.
//
// The smoke archive's first guild has eight media attachments over May and June 2024
// (tests/smoke_archive.py): three images on #art, and on #random a GIF, a video, a
// tall image, a wide one and one whose size Discord did not record.
import type { Locator, Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids from tests/smoke_archive.py.
const NIGHT_ID = '900000000000000002';
const RANDOM_ID = '900000000000000021';
const ART_ID = '900000000000000022';
const PHOTOS_ID = '900000000000000032';

const media = { annotation: { type: ROUTE_ANNOTATION, description: '/media' } };

function tiles(page: Page): Locator {
	return page.locator('main .tile');
}

/** The tiles' accessible names, in grid order. */
async function tileNames(page: Page): Promise<string[]> {
	return tiles(page).evaluateAll((els) => els.map((el) => el.getAttribute('aria-label') ?? ''));
}

/** The screen's search params, to compare without depending on their order. */
function params(page: Page): Record<string, string> {
	return Object.fromEntries(new URL(page.url()).searchParams);
}

// ── Redirects from the old galleries ──

test('/gallery redirects to /media', async ({ page }) => {
	await page.goto('/gallery', { waitUntil: 'networkidle' });
	await expect(page).toHaveURL('/media');
	await expect(page.locator('main h1')).toHaveText('Media');
	await expect(tiles(page)).toHaveCount(8);
});

test('/gallery redirects to /media, keeping the selected guild', async ({ page }) => {
	await page.goto(`/gallery?guild=${NIGHT_ID}`, { waitUntil: 'networkidle' });
	await expect(page).toHaveURL(`/media?guild=${NIGHT_ID}`);
	await expect(page.getByRole('img', { name: 'moonrise.png' })).toBeVisible();
});

test("a channel's gallery redirects to /media filtered to that channel", async ({ page }) => {
	await page.goto(`/channel/${ART_ID}/gallery`, { waitUntil: 'networkidle' });
	await expect(page).toHaveURL(`/media?channel=${ART_ID}`);
	await expect(page.getByLabel('Channel')).toHaveValue(ART_ID);
	await expect.poll(() => tileNames(page)).toEqual([
		'Image: another.png',
		'Image: drawing.png',
		'Image: sketch.png'
	]);
});

test("a channel's gallery redirect keeps the selected guild", async ({ page }) => {
	await page.goto(`/channel/${PHOTOS_ID}/gallery?guild=${NIGHT_ID}`, { waitUntil: 'networkidle' });
	await expect(page).toHaveURL(/^[^?]*\/media\?/);
	await expect.poll(() => params(page)).toEqual({ guild: NIGHT_ID, channel: PHOTOS_ID });
	await expect(page.getByRole('img', { name: 'moonrise.png' })).toBeVisible();
});

test("a channel's gallery without a guild selects the guild holding the channel", async ({ page }) => {
	await page.goto(`/channel/${PHOTOS_ID}/gallery`, { waitUntil: 'networkidle' });
	await expect(page.getByRole('button', { name: 'Guild: Night Owls' })).toBeVisible();
	await expect(page).toHaveURL(/^[^?]*\/media\?/);
	await expect.poll(() => params(page)).toEqual({ guild: NIGHT_ID, channel: PHOTOS_ID });
	await expect(page.getByLabel('Channel')).toHaveValue(PHOTOS_ID);
	await expect(page.getByRole('img', { name: 'moonrise.png' })).toBeVisible();
});

// ── Filters in the URL ──

test('a type chip filters the grid, is kept in the URL and survives a reload', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	await expect(tiles(page)).toHaveCount(8);
	const types = page.getByRole('group', { name: 'Type' });
	await expect(types.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');

	await types.getByRole('button', { name: 'Videos' }).click();
	await expect(page).toHaveURL('/media?type=video');
	await expect.poll(() => tileNames(page)).toEqual(['Video: clip.webm']);
	await expect(page.locator('main h1 + .total')).toHaveText('1 item');

	await page.reload({ waitUntil: 'networkidle' });
	await expect(types.getByRole('button', { name: 'Videos' })).toHaveAttribute('aria-pressed', 'true');
	await expect.poll(() => tileNames(page)).toEqual(['Video: clip.webm']);

	await types.getByRole('button', { name: 'GIFs' }).click();
	await expect(page).toHaveURL('/media?type=gif');
	await expect.poll(() => tileNames(page)).toEqual(['GIF: wumpus-dance.gif']);

	await types.getByRole('button', { name: 'All' }).click();
	await expect(page).toHaveURL('/media');
	await expect(tiles(page)).toHaveCount(8);
});

test('the channel select filters the grid, is kept in the URL and survives a reload', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	await page.getByLabel('Channel').selectOption({ label: '#random' });
	await expect(page).toHaveURL(`/media?channel=${RANDOM_ID}`);
	const onRandom = [
		'Image: panorama.png',
		'Video: clip.webm',
		'Image: unmeasured.png',
		'Image: tall-poster.png',
		'GIF: wumpus-dance.gif'
	];
	await expect.poll(() => tileNames(page)).toEqual(onRandom);

	await page.reload({ waitUntil: 'networkidle' });
	await expect(page.getByLabel('Channel')).toHaveValue(RANDOM_ID);
	await expect.poll(() => tileNames(page)).toEqual(onRandom);

	// Filters combine, and the sort is a filter too.
	await page.getByRole('group', { name: 'Type' }).getByRole('button', { name: 'Images' }).click();
	await page.getByLabel('Sort').selectOption('oldest');
	await expect.poll(() => params(page)).toEqual({ channel: RANDOM_ID, type: 'image', sort: 'oldest' });
	await expect.poll(() => tileNames(page)).toEqual([
		'GIF: wumpus-dance.gif',
		'Image: tall-poster.png',
		'Image: unmeasured.png',
		'Image: panorama.png'
	]);
	await expect(page.locator('main .month-label')).toHaveText(['May 2024', 'June 2024']);

	await page.getByLabel('Channel').selectOption({ label: 'All channels' });
	await expect.poll(() => params(page)).toEqual({ type: 'image', sort: 'oldest' });
});

// ── The grid ──

test('month headers stick under the screen header while their month scrolls by', media, async ({ page }) => {
	await page.setViewportSize({ width: 1000, height: 450 });
	await page.goto('/media', { waitUntil: 'networkidle' });
	const main = page.locator('main');
	const header = main.locator('.media-header');
	const months = main.locator('.month');
	await expect(months).toHaveCount(2);
	await expect(main.locator('.month-label')).toHaveText(['June 2024', 'May 2024']);

	/** Each month's header and section top, relative to the bottom of the screen's header. */
	const positions = () =>
		main.evaluate((m) => {
			const headerBottom = m.querySelector('.media-header')!.getBoundingClientRect().bottom;
			return [...m.querySelectorAll('.month')].map((section) => ({
				header: section.querySelector('.month-header')!.getBoundingClientRect().top - headerBottom,
				section: section.getBoundingClientRect().top - headerBottom,
				bottom: section.getBoundingClientRect().bottom - headerBottom
			}));
		});

	// Scrolled partway into June: June's section has gone under the header, its title has not.
	await main.evaluate((m) => (m.scrollTop = 120));
	let [june] = await positions();
	expect(june.section).toBeLessThan(-50);
	expect(Math.abs(june.header)).toBeLessThanOrEqual(1);
	await expect(header).toBeInViewport();

	// Scrolled into May: May's header has taken its place and June's has gone with June.
	const mayTop = (await positions())[1].section;
	await main.evaluate((m, by) => (m.scrollTop += by), mayTop + 60);
	const [juneLater, may] = await positions();
	expect(may.section).toBeLessThan(-50);
	expect(Math.abs(may.header)).toBeLessThanOrEqual(1);
	expect(juneLater.bottom).toBeLessThanOrEqual(0);
});

test('tiles keep their natural aspect ratio in rows of one height', media, async ({ page }) => {
	await page.setViewportSize({ width: 1440, height: 900 });
	await page.goto('/media', { waitUntil: 'networkidle' });
	await expect(tiles(page)).toHaveCount(8);

	/** Each tile's rendered and natural width over height, once its media has loaded. */
	const shapes = () =>
		tiles(page).evaluateAll((els) =>
			els.map((tile) => {
				const media = tile.querySelector('img, video') as HTMLImageElement | HTMLVideoElement;
				const natural =
					media instanceof HTMLVideoElement
						? media.videoWidth / media.videoHeight
						: media.naturalWidth / media.naturalHeight;
				const box = tile.getBoundingClientRect();
				return { name: tile.getAttribute('aria-label'), rendered: box.width / box.height, natural };
			})
		);
	await expect.poll(async () => (await shapes()).every((s) => Number.isFinite(s.natural))).toBe(true);
	// The image with no recorded size starts square and takes its shape once it loads.
	await expect
		.poll(async () => {
			const shape = (await shapes()).find((s) => s.name === 'Image: unmeasured.png')!;
			return Math.abs(shape.rendered / shape.natural - 1);
		})
		.toBeLessThan(0.02);
	for (const shape of await shapes()) {
		expect(Math.abs(shape.rendered / shape.natural - 1), shape.name ?? '').toBeLessThan(0.02);
	}

	// Tiles in a row share its height.
	const spreads = await page.locator('main .row').evaluateAll((els) =>
		els.map((row) => {
			const heights = [...row.children].map((t) => t.getBoundingClientRect().height);
			return Math.max(...heights) - Math.min(...heights);
		})
	);
	for (const spread of spreads) expect(spread).toBeLessThan(0.5);
});

test('videos and GIFs carry a badge; local attachments are served by the portal', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	const video = page.getByRole('button', { name: 'Video: clip.webm' });
	const gif = page.getByRole('button', { name: 'GIF: wumpus-dance.gif' });
	await expect(video.locator('.kind-badge')).toHaveText('Video');
	await expect(video.locator('.kind-badge svg')).toHaveCount(1);
	await expect(gif.locator('.kind-badge')).toHaveText('GIF');
	await expect(page.locator('main .tile[data-kind="image"] .kind-badge')).toHaveCount(0);

	await expect(video.locator('video')).toHaveAttribute('src', /^\/attachments\/.+\/clip\.webm$/);
	await expect(gif.locator('img')).toHaveAttribute('src', /^\/attachments\/.+\/wumpus-dance\.gif$/);
});

test('a tile opens the one lightbox, which steps through every loaded month', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	await page.getByRole('button', { name: 'Image: another.png' }).click();
	const lightbox = page.locator('.lightbox-overlay');
	await expect(lightbox).toHaveCount(1);
	await expect(lightbox.locator('.lightbox-img')).toHaveAttribute('alt', 'another.png');

	// another.png is June's last; the next is May's first.
	await page.keyboard.press('ArrowRight');
	await expect(lightbox).toHaveCount(1);
	await expect(lightbox.locator('.lightbox-img')).toHaveAttribute('alt', 'drawing.png');
	await page.keyboard.press('ArrowLeft');
	await page.keyboard.press('ArrowLeft');
	await expect(lightbox.locator('video.lightbox-img')).toHaveAttribute('src', /clip\.webm$/);

	await page.keyboard.press('Escape');
	await expect(lightbox).toHaveCount(0);
});

test('a month split across pages shows under one header', media, async ({ page }) => {
	// Two attachments a page, so June's three arrive over two pages.
	await page.route(
		(url) => url.pathname.endsWith('/gallery/timeline'),
		async (route) => {
			const url = new URL(route.request().url());
			url.searchParams.set('limit', '2');
			await route.continue({ url: url.href });
		}
	);
	const pages: string[][] = [];
	page.on('response', async (response) => {
		if (!new URL(response.url()).pathname.endsWith('/gallery/timeline')) return;
		const body = (await response.json()) as { groups: { period: string }[] };
		pages.push(body.groups.map((g) => g.period));
	});
	await page.setViewportSize({ width: 1440, height: 900 });
	await page.goto('/media', { waitUntil: 'networkidle' });
	const main = page.locator('main');

	// Pages load as the end of the grid comes into view.
	await expect(tiles(page)).toHaveCount(8);
	await expect(main.getByRole('button', { name: 'Load more' })).toHaveCount(0);
	expect(pages.slice(0, 2)).toEqual([['2024-06'], ['2024-06', '2024-05']]);
	await expect(main.locator('.month-label')).toHaveText(['June 2024', 'May 2024']);
	await expect(main.locator('.month-count')).toHaveText(['3 items', '5 items']);
});

test('Load more pages on, and a month still loading counts what is in', media, async ({ page }) => {
	await page.route(
		(url) => url.pathname.endsWith('/gallery/timeline'),
		async (route) => {
			const url = new URL(route.request().url());
			url.searchParams.set('limit', '2');
			await route.continue({ url: url.href });
		}
	);
	// Nothing comes into view on its own: only Load more pages on.
	await page.addInitScript(() => {
		window.IntersectionObserver = class {
			observe() {}
			unobserve() {}
			disconnect() {}
		} as unknown as typeof IntersectionObserver;
	});
	await page.goto('/media?type=image&sort=oldest', { waitUntil: 'networkidle' });
	const main = page.locator('main');
	await expect(tiles(page)).toHaveCount(2);
	await expect(main.locator('.month-count')).toHaveText(['2+ items']);

	await main.getByRole('button', { name: 'Load more' }).click();
	await expect(tiles(page)).toHaveCount(4);
	await expect(main.locator('.month-count')).toHaveText(['4+ items']);
	await main.getByRole('button', { name: 'Load more' }).click();
	await expect(main.locator('.month-count')).toHaveText(['5 items', '1+ items']);
	await main.getByRole('button', { name: 'Load more' }).click();
	await expect(main.locator('.month-count')).toHaveText(['5 items', '2 items']);
	await expect(main.getByRole('button', { name: 'Load more' })).toHaveCount(0);
});

test('the sidebar’s Media destination opens the Media screen', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const nav = page.getByRole('navigation', { name: 'Destinations' });
	await nav.getByRole('link', { name: 'Media' }).click();
	await expect(page).toHaveURL('/media');
	await expect(nav.getByRole('link', { name: 'Media' })).toHaveAttribute('aria-current', 'page');
});
