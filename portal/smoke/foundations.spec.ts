// The design foundations every route shares (docs/UI_UX_PROPOSAL.md sections 3, 5
// and 6, #57): the two self-hosted typefaces, the canvas colour, icons drawn as SVG
// rather than Unicode glyphs or emoji, motion that collapses to cross-fades under
// reduced motion, and pages that no longer carry their own spinners, centre states
// or load-more buttons.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures.ts';

// Ids from tests/smoke_archive.py. #art has a reply, a file attachment and reactions.
const ART_ID = '900000000000000022';

const SOURCES = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

/** Characters that are icons when they appear in the portal's own markup: arrows,
 * technical and geometric symbols, dingbats and pictographic emoji. */
const GLYPH =
	/[←-⇿⊕-⊡⌀-⏿■-◿☀-➿⟀-⟯⤀-⥿⬀-⯿]|\p{Extended_Pictographic}/u;

const VISITS = ['/', `/channel/${ART_ID}`, '/gallery', '/search?q=hello', '/people', '/archive'];

/** The first family of an element's computed font-family, unquoted. */
async function firstFamily(page: Page, selector: string): Promise<string> {
	const family = await page
		.locator(selector)
		.first()
		.evaluate((el) => getComputedStyle(el).fontFamily);
	return family.split(',')[0].trim().replace(/^["']|["']$/g, '');
}

test('the UI is set in Instrument Sans and timestamps in JetBrains Mono', async ({ page }) => {
	await page.goto(`/channel/${ART_ID}`, { waitUntil: 'networkidle' });
	await expect(page.locator('main time').first()).toBeVisible();

	expect(await firstFamily(page, 'body')).toMatch(/^Instrument Sans/);
	expect(await firstFamily(page, 'main time')).toMatch(/^JetBrains Mono/);
	expect(
		await page.locator('main time').first().evaluate((el) => getComputedStyle(el).fontVariantNumeric)
	).toContain('tabular-nums');
});

test('only Instrument Sans and JetBrains Mono are loaded, from the portal itself', async ({
	page,
	baseURL
}) => {
	const origin = new URL(baseURL ?? '').origin;
	const fontRequests: URL[] = [];
	const foreignStyles: string[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (request.resourceType() === 'font') fontRequests.push(url);
		if (url.origin !== origin && ['font', 'stylesheet'].includes(request.resourceType())) {
			foreignStyles.push(url.href);
		}
	});

	const loaded = new Set<string>();
	for (const url of VISITS) {
		await page.goto(url, { waitUntil: 'networkidle' });
		const families = await page.evaluate(async () => {
			await document.fonts.ready;
			return [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family);
		});
		for (const family of families) loaded.add(family.replace(/^["']|["']$/g, ''));
	}

	expect(foreignStyles, 'no font or stylesheet comes from another origin').toEqual([]);
	expect([...loaded].sort()).toEqual(['Instrument Sans Variable', 'JetBrains Mono Variable']);
	expect(fontRequests.length).toBeGreaterThan(0);
	for (const url of fontRequests) {
		expect(url.origin).toBe(origin);
		expect(url.pathname).toMatch(/\/(instrument-sans|jetbrains-mono)-[\w.-]+\.woff2$/);
	}
});

test("the page's background is the canvas colour", async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const { body, canvas } = await page.evaluate(() => {
		const probe = document.createElement('div');
		probe.style.backgroundColor = 'var(--bg-canvas)';
		document.body.append(probe);
		const colours = {
			body: getComputedStyle(document.body).backgroundColor,
			canvas: getComputedStyle(probe).backgroundColor
		};
		probe.remove();
		return colours;
	});
	expect(canvas).toBe('rgb(10, 10, 12)');
	expect(body).toBe(canvas);
});

test('the sidebar and message cards draw their icons as SVG, not glyphs or emoji', async ({ page }) => {
	await page.goto(`/channel/${ART_ID}`, { waitUntil: 'networkidle' });

	const links = page.locator('.sidebar .nav-item');
	await expect(links).toHaveCount(5);
	for (const link of await links.all()) {
		await expect(link.locator('svg')).toHaveCount(1);
	}
	await expect(page.locator('.sidebar .brand svg')).toHaveCount(1);
	expect(await page.locator('.sidebar').innerText()).not.toMatch(GLYPH);

	const cards = page.locator('main .message-card');
	await expect(cards).toHaveCount(3);
	// A reply's badge and a file attachment each carry an icon.
	await expect(page.locator('main .message-card .card-footer svg')).toHaveCount(1);
	await expect(page.locator('main .message-card .attachment-file svg')).toHaveCount(1);
	// What the card itself prints, without what people wrote or reacted with.
	const chrome = await cards.evaluateAll((elements) =>
		elements.map((card) => {
			const copy = card.cloneNode(true) as HTMLElement;
			copy
				.querySelectorAll('.content, .reactions, .embeds, .author-name, .file-name')
				.forEach((el) => el.remove());
			return copy.textContent ?? '';
		})
	);
	for (const text of chrome) expect(text).not.toMatch(GLYPH);
	// Reactions keep their emoji.
	await expect(page.locator('main .message-card .reaction-emoji').first()).toHaveText('🔥');
});

/** Every animation on the page that moves something, by name. */
async function transformAnimations(page: Page): Promise<string[]> {
	return page.evaluate(() =>
		document.getAnimations().flatMap((animation) => {
			const effect = animation.effect as KeyframeEffect | null;
			const keyframes = effect?.getKeyframes() ?? [];
			const moves = keyframes.some((k) => ['transform', 'translate', 'scale', 'rotate'].some((p) => p in k));
			const name =
				(animation as CSSAnimation).animationName ??
				(animation as CSSTransition).transitionProperty ??
				animation.id;
			return moves ? [`${name} (${animation.playState})`] : [];
		})
	);
}

test('without reduced motion, content rises in as it enters', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await expect(page.locator('main .stat-card').first()).toBeVisible();
	expect(await transformAnimations(page)).toContainEqual(expect.stringMatching(/^enter /));
});

test.describe('with reduced motion', () => {
	test.beforeEach(async ({ page }) => {
		await page.emulateMedia({ reducedMotion: 'reduce' });
		expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
	});

	for (const url of VISITS) {
		test(`${url} runs no transform animation, only cross-fades`, async ({ page }) => {
			await page.goto(url, { waitUntil: 'domcontentloaded' });
			await expect(page.locator('main')).not.toBeEmpty();
			expect(await transformAnimations(page), 'while loading').toEqual([]);

			await page.waitForLoadState('networkidle');
			expect(await transformAnimations(page), 'once loaded').toEqual([]);
		});
	}

	test('content still fades in on the Overview', async ({ page }) => {
		await page.goto('/', { waitUntil: 'networkidle' });
		await expect(page.locator('main .stat-card').first()).toBeVisible();
		const fades = await page.evaluate(() =>
			document
				.getAnimations()
				.filter((a) => (a as CSSAnimation).animationName === 'enter')
				.map((a) => (a.effect as KeyframeEffect).getKeyframes().some((k) => 'opacity' in k))
		);
		expect(fades.length).toBeGreaterThan(0);
		expect(fades.every(Boolean)).toBe(true);
	});

	test('a running scrape job shows its progress without moving it', async ({ page }) => {
		await page.route('**/api/scrape/status', async (route) => {
			const real = await (await route.fetch()).json();
			await route.fulfill({
				json: {
					...real,
					busy: true,
					current_job: {
						id: 'smoke-job',
						guild_id: 1,
						status: 'scraping',
						progress: {
							current_channel: 'general',
							channels_done: 1,
							messages_scraped: 12,
							attachments_found: 4,
							errors: []
						},
						started_at: '2026-01-01T00:00:00Z',
						completed_at: null,
						result: null,
						error_message: null,
						duration_seconds: 4
					}
				}
			});
		});
		await page.goto('/archive', { waitUntil: 'networkidle' });
		await expect(page.getByRole('progressbar', { name: 'Scraping' })).toBeVisible();
		expect(await transformAnimations(page)).toEqual([]);
	});
});

/** Every .svelte file under src/, relative to it. */
function svelteFiles(dir: string): string[] {
	return readdirSync(dir, { recursive: true, encoding: 'utf8' }).filter((file) => file.endsWith('.svelte'));
}

test('no route declares its own spinner, centre state or load-more button', () => {
	const routes = join(SOURCES, 'routes');
	const offences = svelteFiles(routes).flatMap((file) => {
		const source = readFileSync(join(routes, file), 'utf8');
		return [/@keyframes\s+spin\b/, /\.spinner\b/, /\.center-state\b/, /\.load-more(-btn|-row)?\b/]
			.filter((pattern) => pattern.test(source))
			.map((pattern) => `${file}: ${pattern}`);
	});
	expect(offences).toEqual([]);
});

test("no component or route uses a Unicode glyph or emoji as an icon", () => {
	const offences = svelteFiles(SOURCES).flatMap((file) =>
		readFileSync(join(SOURCES, file), 'utf8')
			.split('\n')
			.flatMap((line, i) => (GLYPH.test(line) || /&#x2[0-9a-f]{3};/i.test(line) ? [`${file}:${i + 1}: ${line.trim()}`] : []))
	);
	expect(offences).toEqual([]);
});
