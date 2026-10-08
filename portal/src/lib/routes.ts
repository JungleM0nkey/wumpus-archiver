// Where the portal's screens live. Every in-app link to a person or a channel is built
// here, so a screen that moves changes this module alone. The selected guild is not
// part of these hrefs: in-app navigation carries it (shell.svelte.ts, `carryGuild`).

import { GUILD_PARAM } from './shell.svelte.ts';

/** A person's profile on the People screen. */
export function personHref(userId: string): string {
	return `/people/${encodeURIComponent(userId)}`;
}

/** A channel in Browse; with `message`, opened on that message. */
export function channelHref(channelId: string, opts: { message?: string } = {}): string {
	const href = `/browse/${encodeURIComponent(channelId)}`;
	return opts.message ? `${href}?message=${encodeURIComponent(opts.message)}` : href;
}

/** The Archive screen, where scrape control and local attachments live. */
export const ARCHIVE_HREF = '/archive';

/** Whether `path` is the Archive screen. */
export function isArchivePath(path: string): boolean {
	return path === ARCHIVE_HREF || path.startsWith(`${ARCHIVE_HREF}/`);
}

/** `href` with the `guild` param of `from`, the URL an old route redirects from. */
export function keepingGuild(href: string, from: URL): string {
	const guild = from.searchParams.get(GUILD_PARAM);
	if (!guild) return href;
	const url = new URL(href, from);
	url.searchParams.set(GUILD_PARAM, guild);
	return url.pathname + url.search;
}
