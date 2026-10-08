// The shell every route shares: its tab icon and the sidebar's version badge.
import { readFileSync } from 'node:fs';
import { expect, test } from './fixtures.ts';

const portalPackage = JSON.parse(
	readFileSync(new URL('../package.json', import.meta.url), 'utf8')
) as { version: string };

test('the tab shows the Wumpus Archiver favicon', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	const href = await page.locator('link[rel="icon"]').getAttribute('href');
	expect(href).toBeTruthy();

	const icon = await page.request.get(new URL(href!, page.url()).href);
	expect(icon.status()).toBe(200);
	expect(icon.headers()['content-type']).toContain('image/svg+xml');
	const svg = await icon.text();
	expect(svg).toContain('<title>Wumpus Archiver</title>');
	expect(svg).not.toContain('svelte-logo');
});

test("the version badge shows the portal's package version", async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await expect(page.locator('.sidebar .version')).toHaveText(`v${portalPackage.version}`);
});
