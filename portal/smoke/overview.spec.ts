// The Overview's most active channels lead to the channels themselves.
import { expect, test } from './fixtures.ts';

// Ids and text from tests/smoke_archive.py.
const GENERAL_ID = '900000000000000020';

test('an Overview top channel opens that channel', async ({ page }) => {
	await page.goto('/', { waitUntil: 'networkidle' });
	await page.getByRole('link', { name: '#general' }).click();

	await expect(page).toHaveURL(`/channel/${GENERAL_ID}`);
	await expect(page.locator('main').getByText('Anyone up for a game tonight?')).toBeVisible();
});
