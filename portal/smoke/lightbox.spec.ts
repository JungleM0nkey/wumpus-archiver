// The Lightbox and Browse's tabs (#63). One Lightbox serves the Media screen and
// Browse's Media tab: a modal dialog with the author and a counter, ←/→ through the
// loaded attachments, a filmstrip and the file's details, "Open in conversation" to
// the attachment's message in Browse, and Esc back to the tile it opened from. It
// zooms from the tile with a view transition, and only fades under reduced motion.
//
// Browse's reader has Messages / Media / Pinned tabs, kept in the URL as `tab`.
//
// The smoke archive's first guild has eight media attachments (tests/smoke_archive.py),
// newest first: on #random panorama.png and clip.webm, then another.png on #art (June);
// drawing.png and sketch.png on #art, then a GIF and two images on #random (May).
// #general has two pinned messages and #random one.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Locator, Page } from '@playwright/test';
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids from tests/smoke_archive.py.
const GENERAL_ID = '900000000000000020';
const RANDOM_ID = '900000000000000021';
const ART_ID = '900000000000000022';
const NIGHT_ID = '900000000000000002';
const PHOTOS_ID = '900000000000000032';
/** "Another drawing" on #art, which carries another.png. */
const ANOTHER_DRAWING_ID = '900000000000001010';
/** "Here is mine, plus the notes" on #art, which carries drawing.png. */
const HERE_IS_MINE_ID = '900000000000001007';
/** "The hello world of June.", #general's newest and pinned. */
const HELLO_ID = '900000000000001009';

const media = { annotation: { type: ROUTE_ANNOTATION, description: '/media' } };
const reader = { annotation: { type: ROUTE_ANNOTATION, description: '/browse/[channel]' } };

const SOURCES = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

function lightbox(page: Page): Locator {
	return page.getByRole('dialog');
}

/** The tile of attachment `filename` in the grid. */
function tile(page: Page, name: string): Locator {
	return page.locator('main .tile').filter({ has: page.locator(`[alt="${name}"], video[src$="/${name}"]`) });
}

/** What the Lightbox shows: its media's file name. */
async function shown(page: Page): Promise<string> {
	return lightbox(page)
		.locator('.stage .media')
		.evaluate((el) => (el as HTMLImageElement).alt || (el as HTMLVideoElement).src.split('/').pop()!);
}

/** The card of message `id` in the reader. */
function card(page: Page, id: string): Locator {
	return page.locator(`main [data-message-id="${id}"]`);
}

/** Every source file under src, as [path relative to src, content]. */
function sources(): [string, string][] {
	return readdirSync(SOURCES, { recursive: true, encoding: 'utf8' })
		.filter((file) => /\.(svelte|ts)$/.test(file))
		.map((file) => [file.split(sep).join('/'), readFileSync(join(SOURCES, file), 'utf8')]);
}

// ── One Lightbox ──────────────────────────────────────────────────────────────

test('exactly one Lightbox exists, and both the Media screen and Browse use it', () => {
	const files = sources();
	const importing = (name: string) =>
		files.filter(([, text]) => new RegExp(`import \\w+ from '[^']*/${name}'`).test(text)).map(([f]) => f);
	// The Lightbox draws its own dialog over the page; the only other <dialog> is the
	// shell's Dialog primitive (#59: the palette, the keyboard map, the mobile sheet).
	// MediaTimeline is the only screen part that renders the Lightbox.
	expect(files.filter(([, text]) => /<dialog\b/.test(text)).map(([f]) => f).sort()).toEqual([
		'lib/components/Lightbox.svelte',
		'lib/components/ui/Dialog.svelte'
	]);
	expect(files.filter(([f]) => /lightbox/i.test(f.split('/').pop()!)).map(([f]) => f)).toEqual([
		'lib/components/Lightbox.svelte'
	]);
	expect(importing('Lightbox.svelte')).toEqual(['lib/components/MediaTimeline.svelte']);
	expect(importing('MediaTimeline.svelte').sort()).toEqual([
		'routes/browse/[channel]/+page.svelte',
		'routes/media/+page.svelte'
	]);
});

test('a tile opens the Lightbox: author, counter, details, filmstrip', media, async ({ page }) => {
	await page.setViewportSize({ width: 1440, height: 900 });
	await page.goto('/media', { waitUntil: 'networkidle' });
	await tile(page, 'another.png').click();

	const dialog = lightbox(page);
	await expect(dialog).toBeVisible();
	await expect(dialog).toHaveAccessibleName('Image: another.png');
	expect(await dialog.evaluate((d) => (d as HTMLDialogElement).open && d.matches(':modal'))).toBe(true);
	await expect(dialog.locator('.author')).toHaveText('Alice');
	await expect(dialog.locator('.where')).toContainText('#art');
	await expect(dialog.locator('.counter')).toHaveText('3 of 8');

	const details = dialog.getByRole('complementary', { name: 'File details' });
	await expect(details.getByRole('heading')).toHaveText('another.png');
	const meta = await details.locator('.meta > div').evaluateAll((rows) =>
		rows.map((row) => [row.querySelector('dt')!.textContent, row.querySelector('dd')!.textContent])
	);
	expect(meta.map(([term]) => term)).toEqual(['Size', 'Dimensions', 'Type', 'Posted']);
	expect(Object.fromEntries(meta)).toMatchObject({ Dimensions: '4 × 3', Type: 'image/png' });
	expect(Object.fromEntries(meta).Size).toMatch(/^\d+ B$/);
	expect(Object.fromEntries(meta).Posted).toMatch(/2024/);

	const strip = dialog.getByRole('navigation', { name: 'Filmstrip' });
	await expect(strip.getByRole('button')).toHaveCount(8);
	await expect(strip.locator('[aria-current="true"]')).toHaveAccessibleName('Image 3: another.png');
});

test('→ twice, then "Open in conversation", lands in Browse on that attachment’s message', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	await tile(page, 'panorama.png').click();
	const dialog = lightbox(page);
	await expect(dialog.locator('.counter')).toHaveText('1 of 8');
	expect(await shown(page)).toBe('panorama.png');

	await page.keyboard.press('ArrowRight');
	await expect(dialog.locator('.counter')).toHaveText('2 of 8');
	expect(await shown(page)).toBe('clip.webm');
	await page.keyboard.press('ArrowRight');
	await expect(dialog.locator('.counter')).toHaveText('3 of 8');
	expect(await shown(page)).toBe('another.png');

	await dialog.getByRole('link', { name: 'Open in conversation' }).click();
	await expect(page).toHaveURL(`/browse/${ART_ID}?message=${ANOTHER_DRAWING_ID}`);
	await expect(lightbox(page)).toHaveCount(0);
	await expect(card(page, ANOTHER_DRAWING_ID)).toHaveAttribute('aria-current', 'true');
	await expect(card(page, ANOTHER_DRAWING_ID)).toBeInViewport();
	await expect(page.locator('main').getByRole('heading', { level: 1 })).toHaveText('art');
});

test('← → step through every loaded attachment, and stop at either end', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	await tile(page, 'panorama.png').click();
	const dialog = lightbox(page);
	const previous = dialog.getByRole('button', { name: 'Previous' });
	const next = dialog.getByRole('button', { name: 'Next' });
	await expect(previous).toBeDisabled();
	await page.keyboard.press('ArrowLeft');
	await expect(dialog.locator('.counter')).toHaveText('1 of 8');

	for (let i = 2; i <= 8; i++) {
		await next.click();
		await expect(dialog.locator('.counter')).toHaveText(`${i} of 8`);
	}
	await expect(next).toBeDisabled();
	expect(await shown(page)).toBe('wumpus-dance.gif');
	await page.keyboard.press('ArrowRight');
	await expect(dialog.locator('.counter')).toHaveText('8 of 8');

	// The filmstrip jumps straight to one.
	await dialog.getByRole('navigation', { name: 'Filmstrip' }).getByRole('button', { name: 'Image 4: drawing.png' }).click();
	await expect(dialog.locator('.counter')).toHaveText('4 of 8');
	expect(await shown(page)).toBe('drawing.png');
	await expect(dialog.locator('.author')).toHaveText('Bob');
});

test('Esc closes the Lightbox and returns focus to the tile it opened from', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	const opener = tile(page, 'sketch.png');
	await opener.click();
	await expect(lightbox(page)).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(lightbox(page)).toHaveCount(0);
	await expect(opener).toBeFocused();

	// From the keyboard, and after stepping away from it.
	const gif = tile(page, 'wumpus-dance.gif');
	await gif.focus();
	await page.keyboard.press('Enter');
	await expect(lightbox(page)).toBeVisible();
	await page.keyboard.press('ArrowLeft');
	await page.keyboard.press('ArrowLeft');
	await expect(lightbox(page).locator('.counter')).toHaveText('6 of 8');
	await page.keyboard.press('Escape');
	await expect(lightbox(page)).toHaveCount(0);
	await expect(gif).toBeFocused();

	// The close button does the same.
	await opener.click();
	await lightbox(page).getByRole('button', { name: 'Close' }).click();
	await expect(lightbox(page)).toHaveCount(0);
	await expect(opener).toBeFocused();
});

test('Esc while the Lightbox is still zooming in closes it once it has opened', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	// The dialog is open, and has focus, before its zoom in ends: press Esc right then,
	// the moment the dialog opens, as a reader quick on the key can.
	const pressed = page.evaluate(
		() =>
			new Promise<void>((resolve) => {
				const observer = new MutationObserver(() => {
					const dialog = document.querySelector('dialog[open]');
					if (!dialog) return;
					observer.disconnect();
					queueMicrotask(() => {
						const init = { key: 'Escape', bubbles: true, cancelable: true };
						(document.activeElement ?? dialog).dispatchEvent(new KeyboardEvent('keydown', init));
						resolve();
					});
				});
				observer.observe(document.body, { subtree: true, attributeFilter: ['open'] });
			})
	);
	const opener = tile(page, 'sketch.png');
	await opener.click();
	await pressed;
	await expect(lightbox(page)).toHaveCount(0);
	await expect(opener).toBeFocused();
});

test('focus stays inside the Lightbox while it is open', media, async ({ page }) => {
	await page.goto('/media', { waitUntil: 'networkidle' });
	await tile(page, 'another.png').click();
	await expect(lightbox(page)).toBeVisible();
	for (let i = 0; i < 14; i++) {
		await page.keyboard.press('Tab');
		const inside = await page.evaluate(() => {
			const active = document.activeElement;
			return !!active && active !== document.body && !!active.closest('dialog');
		});
		expect(inside, `focus after ${i + 1} Tab presses`).toBe(true);
	}
});

test('the Lightbox zooms from its tile with a view transition, and back', media, async ({ page }) => {
	await page.addInitScript(() => {
		const calls: string[][] = [];
		(window as unknown as { zooms: string[][] }).zooms = calls;
		const start = document.startViewTransition.bind(document);
		document.startViewTransition = ((update: ViewTransitionUpdateCallback) => {
			// What carries the zoom's name when the old state is captured.
			const named = [...document.querySelectorAll<HTMLElement>('main img, main video, dialog img')]
				.filter((el) => el.style.viewTransitionName === 'lightbox-media')
				.map((el) => `${el.closest('dialog') ? 'lightbox' : 'tile'}:${el.getAttribute('alt')}`);
			calls.push(named);
			return start(update);
		}) as typeof document.startViewTransition;
	});
	await page.goto('/media', { waitUntil: 'networkidle' });
	// The pseudo-elements that animate while it opens.
	await page.evaluate(() => {
		const seen = new Set<string>();
		(window as unknown as { animated: Set<string> }).animated = seen;
		const watch = () => {
			for (const a of document.getAnimations()) {
				const pseudo = (a.effect as KeyframeEffect).pseudoElement;
				if (pseudo) seen.add(pseudo);
			}
			requestAnimationFrame(watch);
		};
		watch();
	});
	const opener = tile(page, 'another.png');
	await opener.click();
	await expect(lightbox(page)).toBeVisible();
	// The media moves and resizes from the tile (its group), and the tile cross-fades into it.
	await expect
		.poll(() => page.evaluate(() => [...(window as unknown as { animated: Set<string> }).animated].sort()))
		.toEqual([
			'::view-transition-group(lightbox-media)',
			'::view-transition-new(lightbox-media)',
			'::view-transition-old(lightbox-media)'
		]);
	await page.keyboard.press('Escape');
	await expect(lightbox(page)).toHaveCount(0);
	const zooms = await page.evaluate(() => (window as unknown as { zooms: string[][] }).zooms);
	expect(zooms).toEqual([['tile:another.png'], ['lightbox:another.png']]);
	// Once it is done, nothing keeps the name.
	await expect
		.poll(() =>
			page.evaluate(
				() =>
					[...document.querySelectorAll<HTMLElement>('img, video')].filter(
						(el) => el.style.viewTransitionName !== ''
					).length
			)
		)
		.toBe(0);
});

test.describe('with reduced motion', () => {
	test.beforeEach(async ({ page }) => {
		await page.emulateMedia({ reducedMotion: 'reduce' });
	});

	test('the Lightbox only fades in, with no zoom', media, async ({ page }) => {
		await page.addInitScript(() => {
			(window as unknown as { transitions: number }).transitions = 0;
			const start = document.startViewTransition.bind(document);
			document.startViewTransition = ((update: ViewTransitionUpdateCallback) => {
				(window as unknown as { transitions: number }).transitions++;
				return start(update);
			}) as typeof document.startViewTransition;
		});
		await page.goto('/media', { waitUntil: 'networkidle' });
		await tile(page, 'another.png').click();
		await expect(lightbox(page)).toBeVisible();
		const animations = await page.evaluate(() =>
			document.getAnimations().map((a) => ({
				name: (a as CSSAnimation).animationName,
				moves: (a.effect as KeyframeEffect)
					.getKeyframes()
					.some((k) => ['transform', 'translate', 'scale'].some((p) => p in k))
			}))
		);
		expect(animations.filter((a) => a.moves)).toEqual([]);
		// The chrome still fades in after the scrim.
		expect(animations.map((a) => a.name)).toContain('enter');
		expect(await page.evaluate(() => (window as unknown as { transitions: number }).transitions)).toBe(0);
		await page.keyboard.press('Escape');
		await expect(lightbox(page)).toHaveCount(0);
	});
});

test('on a phone, the Lightbox fits the screen', media, async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 844 });
	await page.goto('/media', { waitUntil: 'networkidle' });
	await tile(page, 'panorama.png').click();
	const dialog = lightbox(page);
	await expect(dialog).toBeVisible();
	expect(await dialog.evaluate((d) => d.scrollWidth <= d.clientWidth)).toBe(true);
	for (const part of ['.top-bar', '.stage .media', '.filmstrip']) {
		const box = (await dialog.locator(part).boundingBox())!;
		expect(box.x, part).toBeGreaterThanOrEqual(0);
		expect(box.x + box.width, part).toBeLessThanOrEqual(390);
	}
	await expect(dialog.getByRole('link', { name: 'Open in conversation' })).toBeVisible();
});

// ── Browse's tabs ─────────────────────────────────────────────────────────────

function tabs(page: Page): Locator {
	return page.getByRole('tablist', { name: 'Channel views' });
}

test('the reader opens on the Messages tab', reader, async ({ page }) => {
	await page.goto(`/browse/${ART_ID}`, { waitUntil: 'networkidle' });
	await expect(tabs(page).getByRole('tab')).toHaveText(['Messages', 'Media', 'Pinned']);
	await expect(tabs(page).getByRole('tab', { name: 'Messages' })).toHaveAttribute('aria-selected', 'true');
	await expect(page.getByRole('tabpanel', { name: 'Messages' })).toContainText('Another drawing');
});

test('the Media tab shows only the channel’s media, and survives a reload', reader, async ({ page }) => {
	const timeline: URLSearchParams[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (url.pathname.endsWith('/gallery/timeline')) timeline.push(url.searchParams);
	});
	await page.goto(`/browse/${ART_ID}`, { waitUntil: 'networkidle' });
	await tabs(page).getByRole('tab', { name: 'Media' }).click();
	await expect(page).toHaveURL(`/browse/${ART_ID}?tab=media`);
	await expect(tabs(page).getByRole('tab', { name: 'Media' })).toHaveAttribute('aria-selected', 'true');
	const panel = page.getByRole('tabpanel', { name: 'Media' });
	const names = () => panel.locator('.tile').evaluateAll((els) => els.map((el) => el.getAttribute('aria-label')));
	const onArt = ['Image: another.png', 'Image: drawing.png', 'Image: sketch.png'];
	await expect.poll(names).toEqual(onArt);
	await expect(panel.locator('.month-label')).toHaveText(['June 2024', 'May 2024']);
	await expect(page.getByRole('tabpanel', { name: 'Messages' })).toBeHidden();
	expect(timeline.map((p) => p.get('channel_id'))).toEqual([ART_ID]);

	await page.reload({ waitUntil: 'networkidle' });
	await expect(tabs(page).getByRole('tab', { name: 'Media' })).toHaveAttribute('aria-selected', 'true');
	await expect.poll(names).toEqual(onArt);

	// Back to Messages: the param goes, and the feed is there.
	await tabs(page).getByRole('tab', { name: 'Messages' }).click();
	await expect(page).toHaveURL(`/browse/${ART_ID}`);
	await expect(page.getByRole('tabpanel', { name: 'Messages' })).toContainText('Another drawing');
});

test('the tab is kept beside the selected guild', reader, async ({ page }) => {
	await page.goto(`/browse/${PHOTOS_ID}?guild=${NIGHT_ID}`, { waitUntil: 'networkidle' });
	await tabs(page).getByRole('tab', { name: 'Media' }).click();
	await expect
		.poll(() => Object.fromEntries(new URL(page.url()).searchParams))
		.toEqual({ guild: NIGHT_ID, tab: 'media' });
	await expect(page.getByRole('tabpanel', { name: 'Media' }).getByRole('img', { name: 'moonrise.png' })).toBeVisible();
	await page.reload({ waitUntil: 'networkidle' });
	await expect(page.getByRole('button', { name: 'Guild: Night Owls' })).toBeVisible();
	await expect(page.getByRole('tabpanel', { name: 'Media' }).getByRole('img', { name: 'moonrise.png' })).toBeVisible();
});

test('the tabs move with the arrow keys', reader, async ({ page }) => {
	await page.goto(`/browse/${ART_ID}`, { waitUntil: 'networkidle' });
	await tabs(page).getByRole('tab', { name: 'Messages' }).focus();
	await page.keyboard.press('ArrowRight');
	await expect(page).toHaveURL(`/browse/${ART_ID}?tab=media`);
	await expect(tabs(page).getByRole('tab', { name: 'Media' })).toBeFocused();
	await page.keyboard.press('End');
	await expect(page).toHaveURL(`/browse/${ART_ID}?tab=pinned`);
	await page.keyboard.press('ArrowRight');
	await expect(page).toHaveURL(`/browse/${ART_ID}`);
});

test('the Media tab’s Lightbox opens the attachment’s message in the Messages tab', reader, async ({ page }) => {
	await page.goto(`/browse/${ART_ID}?tab=media`, { waitUntil: 'networkidle' });
	const opener = page.getByRole('tabpanel', { name: 'Media' }).locator('.tile').first();
	await opener.click();
	const dialog = lightbox(page);
	await expect(dialog.locator('.counter')).toHaveText('1 of 3');
	await page.keyboard.press('ArrowRight');
	expect(await shown(page)).toBe('drawing.png');
	await page.keyboard.press('Escape');
	await expect(opener).toBeFocused();

	await opener.click();
	await expect(dialog.locator('.counter')).toHaveText('1 of 3');
	await page.keyboard.press('ArrowRight');
	await expect(dialog.locator('.counter')).toHaveText('2 of 3');
	await dialog.getByRole('link', { name: 'Open in conversation' }).click();
	await expect(page).toHaveURL(`/browse/${ART_ID}?message=${HERE_IS_MINE_ID}`);
	await expect(tabs(page).getByRole('tab', { name: 'Messages' })).toHaveAttribute('aria-selected', 'true');
	await expect(card(page, HERE_IS_MINE_ID)).toHaveAttribute('aria-current', 'true');
});

test('the Pinned tab lists exactly the channel’s pinned messages', reader, async ({ page }) => {
	const requests: string[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (url.pathname === `/api/channels/${GENERAL_ID}/messages`) requests.push(url.search);
	});
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	await tabs(page).getByRole('tab', { name: 'Pinned' }).click();
	await expect(page).toHaveURL(`/browse/${GENERAL_ID}?tab=pinned`);
	const panel = page.getByRole('tabpanel', { name: 'Pinned' });
	await expect(panel.locator('.pinned-total')).toHaveText('2 pinned messages');
	await expect(panel.locator('.message-card .content')).toHaveText([
		'The hello world of June.',
		'Anyone up for a game tonight?'
	]);
	// #random's pinned message is not #general's.
	await expect(panel.getByText('Agreed.')).toHaveCount(0);
	expect(requests).toContain('?limit=50&pinned=true');

	await page.reload({ waitUntil: 'networkidle' });
	await expect(tabs(page).getByRole('tab', { name: 'Pinned' })).toHaveAttribute('aria-selected', 'true');
	await expect(panel.locator('.message-card')).toHaveCount(2);

	// A pinned message opens in the conversation.
	await panel.getByRole('link', { name: 'Jump to message' }).first().click();
	await expect(page).toHaveURL(`/browse/${GENERAL_ID}?message=${HELLO_ID}`);
	await expect(card(page, HELLO_ID)).toHaveAttribute('aria-current', 'true');
});

test('a channel with nothing pinned says so', reader, async ({ page }) => {
	await page.goto(`/browse/${ART_ID}?tab=pinned`, { waitUntil: 'networkidle' });
	await expect(page.getByRole('tabpanel', { name: 'Pinned' })).toContainText('No pinned messages in this channel.');
	await page.goto(`/browse/${RANDOM_ID}?tab=pinned`, { waitUntil: 'networkidle' });
	await expect(page.getByRole('tabpanel', { name: 'Pinned' }).locator('.message-card .content')).toHaveText(['Agreed.']);
});

test('each tab keeps its place while another is shown', reader, async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 400 });
	await page.goto(`/browse/${GENERAL_ID}`, { waitUntil: 'networkidle' });
	const main = page.locator('main');
	const bottom = await main.evaluate((m) => m.scrollTop);
	expect(bottom).toBeGreaterThan(0);
	// Clicked without Playwright first scrolling the sticky header's tab "into view".
	await tabs(page).getByRole('tab', { name: 'Pinned' }).dispatchEvent('click');
	await expect(page.getByRole('tabpanel', { name: 'Pinned' }).locator('.message-card')).toHaveCount(2);
	expect(await main.evaluate((m) => m.scrollTop)).toBe(0);
	await tabs(page).getByRole('tab', { name: 'Messages' }).dispatchEvent('click');
	await expect(page).toHaveURL(`/browse/${GENERAL_ID}`);
	expect(await main.evaluate((m) => m.scrollTop)).toBe(bottom);
});
