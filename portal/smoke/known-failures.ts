// Failures the smoke suite knows the portal has today, each owned by the ticket
// that removes it. Everything else a route does wrong fails its test.
//
// An entry is as narrow as the failure: one route, one request, one status. It is
// also checked to still happen, so the ticket that fixes it gets a failing smoke
// test until it deletes the entry here.

export interface KnownFailure {
	/** The issue that fixes it and removes this entry. */
	ticket: string;
	/** Why the request fails. */
	why: string;
	/** The route test it is expected in, as in ROUTES (for example '/users/[id]'). */
	route: string;
	/** The failing request: its method, API path and status. */
	method: string;
	path: string;
	status: number;
	/** Narrows the match further on the request's query string. */
	query?: (params: URLSearchParams) => boolean;
}

export const KNOWN_FAILURES: KnownFailure[] = [];
