// A profile's recent messages are that author's newest messages, read with no query.
// The guard fails the test on any 4xx the page receives.
import { ROUTE_ANNOTATION, expect, test } from './fixtures.ts';

// Ids and text from tests/smoke_archive.py.
const ALICE_ID = '900000000000000100';
const ALICE_NEWEST_FIRST = [
	'Another drawing',
	'June already?',
	'My first sketch',
	'Agreed.',
	'Anyone up for a game tonight?',
	'Welcome to the smoke test guild!'
];

test(
	"a profile's recent messages are the author's newest messages",
	{ annotation: { type: ROUTE_ANNOTATION, description: '/users/[id]' } },
	async ({ page }) => {
		await page.goto(`/users/${ALICE_ID}`, { waitUntil: 'networkidle' });

		const read = page.waitForRequest((request) => new URL(request.url()).pathname === '/api/search');
		await page.getByRole('button', { name: 'Load Messages' }).click();
		const params = new URL((await read).url()).searchParams;
		expect(params.get('author_id')).toBe(ALICE_ID);
		expect(params.has('q')).toBe(false);

		await expect(page.getByRole('button', { name: 'Loaded' })).toBeVisible();
		const contents = page.locator('main .messages-list .message-card .content');
		await expect(contents).toHaveText(ALICE_NEWEST_FIRST);
	}
);
