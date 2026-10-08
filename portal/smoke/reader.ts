// Helpers for the smoke tests of Browse's reader (reader.spec.ts, browse.spec.ts).
import type { Locator, Page } from '@playwright/test';
import { expect } from './fixtures.ts';

/** Answer every channel messages request with at most `limit` messages. */
export async function narrowPages(page: Page, limit: number): Promise<void> {
	await page.route(
		(url) => url.pathname.startsWith('/api/channels/') && url.pathname.endsWith('/messages'),
		async (route) => {
			const url = new URL(route.request().url());
			url.searchParams.set('limit', String(limit));
			await route.continue({ url: url.href });
		}
	);
}

/**
 * The text of the message in `scope` that says `text`: its own content, not a reply's
 * snippet of it (#61).
 */
export function said(scope: Page | Locator, text: string): Locator {
	return scope.locator('[data-message-id] .content').getByText(text, { exact: true });
}

/** The top of the message whose text is `text`, in viewport pixels. */
export async function topOf(page: Page, text: string): Promise<number> {
	const box = await said(page.locator('main'), text).boundingBox();
	expect(box, `${text} is laid out`).not.toBeNull();
	return box!.y;
}
