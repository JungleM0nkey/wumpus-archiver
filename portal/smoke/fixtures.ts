// The smoke suite's test, with a guard on every page it opens.
//
// The guard records what a route does wrong while the test runs: an uncaught page
// error, a console error, a same-origin response with a 4xx/5xx status, or a failed
// /api request. When the test ends it fails on anything recorded that is not one of
// the KNOWN_FAILURES listed for the test's route, and on any known failure for that
// route that no longer happens.
//
// Requests to other origins (web fonts) are answered with an empty 200, so the
// suite needs no network and a missing font never reads as a failure.
import { test as base, expect, type ConsoleMessage, type Page, type Response } from '@playwright/test';
import { KNOWN_FAILURES, type KnownFailure } from './known-failures.ts';

/** The annotation type a test carries to name its route, as in ROUTES. */
export const ROUTE_ANNOTATION = 'route';

interface FailedRequest {
	method: string;
	url: URL;
	status: number | null;
	error?: string;
}

export class PageGuard {
	private readonly pageErrors: Error[] = [];
	private readonly consoleErrors: ConsoleMessage[] = [];
	private readonly failedRequests: FailedRequest[] = [];

	constructor(page: Page, origin: string) {
		page.on('pageerror', (error) => this.pageErrors.push(error));
		page.on('console', (message) => {
			if (message.type() === 'error') this.consoleErrors.push(message);
		});
		page.on('response', (response: Response) => {
			const url = new URL(response.url());
			if (url.origin === origin && response.status() >= 400) {
				this.failedRequests.push({
					method: response.request().method(),
					url,
					status: response.status()
				});
			}
		});
		page.on('requestfailed', (request) => {
			const url = new URL(request.url());
			if (url.origin === origin && url.pathname.startsWith('/api/')) {
				this.failedRequests.push({
					method: request.method(),
					url,
					status: null,
					error: request.failure()?.errorText
				});
			}
		});
	}

	/** Every problem not covered by `known`, and every entry of `known` that did not happen. */
	verify(known: KnownFailure[]): { problems: string[]; stale: KnownFailure[] } {
		const seen = new Set<KnownFailure>();
		const covered = new Set<string>();
		const problems: string[] = [];

		for (const request of this.failedRequests) {
			const entry = known.find(
				(k) =>
					k.method === request.method &&
					k.path === request.url.pathname &&
					k.status === request.status &&
					(k.query?.(request.url.searchParams) ?? true)
			);
			if (entry) {
				seen.add(entry);
				covered.add(request.url.href);
			} else {
				const outcome = request.status ?? request.error ?? 'failed';
				problems.push(`${request.method} ${request.url.pathname}${request.url.search} -> ${outcome}`);
			}
		}
		for (const message of this.consoleErrors) {
			// The browser logs each failed response once more as a console error; a
			// covered request's line is covered with it, any other one is reported.
			const resource = message.location().url;
			if (message.text().startsWith('Failed to load resource') && covered.has(resource)) continue;
			problems.push(`console error: ${message.text()}${resource ? ` (${resource})` : ''}`);
		}
		for (const error of this.pageErrors) {
			problems.push(`page error: ${error.stack ?? error.message}`);
		}
		return { problems, stale: known.filter((k) => !seen.has(k)) };
	}
}

export const test = base.extend<{ guard: PageGuard }>({
	guard: [
		async ({ page, baseURL }, use, testInfo) => {
			const origin = new URL(baseURL ?? '').origin;
			await page.route(
				(url) => url.origin !== origin,
				(route) => route.fulfill({ status: 200, body: '' })
			);
			const guard = new PageGuard(page, origin);
			await use(guard);

			const route = testInfo.annotations.find((a) => a.type === ROUTE_ANNOTATION)?.description;
			const known = KNOWN_FAILURES.filter((k) => k.route === route);
			const { problems, stale } = guard.verify(known);
			expect(problems, `${route ?? testInfo.title} must load without errors`).toEqual([]);
			if (testInfo.status === testInfo.expectedStatus) {
				const fixed = stale.map((k) => `${k.method} ${k.path} -> ${k.status} (${k.ticket}: ${k.why})`);
				expect(fixed, 'these known failures no longer happen: remove them from KNOWN_FAILURES').toEqual([]);
			}
		},
		{ auto: true }
	]
});

export { expect };
