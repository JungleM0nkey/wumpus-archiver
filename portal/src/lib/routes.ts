// Where the portal's screens live. Every in-app link to a person or a channel is built
// here, so a screen that moves changes this module alone. The selected guild is not
// part of these hrefs: in-app navigation carries it (shell.svelte.ts, `carryGuild`).

/** A person's profile on the People screen. */
export function personHref(userId: string): string {
	return `/people/${encodeURIComponent(userId)}`;
}

/** A channel's messages; with `message`, opened on that message. */
export function channelHref(channelId: string, opts: { message?: string } = {}): string {
	const href = `/channel/${encodeURIComponent(channelId)}`;
	return opts.message ? `${href}?message=${encodeURIComponent(opts.message)}` : href;
}
