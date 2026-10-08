// The People screen ranks authors 1..N however many pages it has loaded.
import { expect, test } from './fixtures.ts';

// tests/smoke_archive.py holds 120 authors; the People screen loads 50 at a time.
const AUTHORS = 120;

test('People ranks run 1..N without gaps or repeats after two Load more clicks', async ({ page }) => {
	await page.goto('/users', { waitUntil: 'networkidle' });
	const ranks = page.locator('main .user-rank');
	await expect(ranks).toHaveCount(50);

	const loadMore = page.getByRole('button', { name: /Load more/ });
	await loadMore.click();
	await expect(ranks).toHaveCount(100);
	await loadMore.click();
	await expect(ranks).toHaveCount(AUTHORS);
	await expect(loadMore).toHaveCount(0);

	const expected = Array.from({ length: AUTHORS }, (_, i) => `#${i + 1}`);
	expect(await ranks.allInnerTexts()).toEqual(expected);
});
