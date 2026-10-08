// The shell's API for routes: which guild a screen shows, and where page content scrolls.
//
// The selected guild
//   `shell.guild` is the guild every screen shows, `shell.guilds` every archived guild.
//   The selection is part of the URL as `?guild=<id>`, so a link to a screen is
//   shareable and survives a reload; without the param it is the first guild. Read
//   `shell.guild` when the route mounts (in onMount, say). Switching guild remounts the
//   route, so a route never watches the selection, and it never calls getGuilds().
//   Links need nothing either: a navigation inside the portal keeps the current `guild`
//   param. `withGuild(href)` spells it out for an href that must carry it on its own,
//   such as one opened in a new tab.
//
//   A screen about one channel or one author belongs to one guild. Switching guild
//   there goes to its destination's index instead (GUILD_BOUND below; a route that
//   takes such an id adds itself there), and `guildHolding(channelId)` selects the
//   guild that holds a channel when a link names it without one. A screen whose
//   params name a channel or an author stays, without them: GUILD_BOUND_PARAMS lists
//   such params, and GUILD_BOUND_REWRITES rewrites a screen's own (Search's chips).
//
// The scroll container
//   Page content scrolls in one element, the shell's <main> (`shell.scroller`), which
//   keeps each history entry's scroll position and restores it on back/forward. A route
//   never gives its own content an overflow; it uses `shell.scroller` where it needs
//   scrollTop/scrollHeight or an IntersectionObserver root. A pane that stays in view
//   (a header, a filter list) is `position: sticky; top: 0` inside it, and one that
//   fills the visible height takes `height: var(--shell-viewport-height)`. A sticky
//   header across the top also takes `use:stickyHeader`, so that scrolling something
//   into view (a click, find in page, keyboard focus) stops below it, not under it.
//
// The destinations and the narrow layout
//   DESTINATIONS are the five screens the sidebar, the mobile tab bar, the command
//   palette and ⌘1–5 go to; a route that replaces one changes its entry here. Below
//   768px (`viewport.narrow`) the sidebar becomes a sheet opened from a top bar and a
//   tab bar carries the destinations; `--shell-viewport-height` is then the room
//   between those two bars. A screen never hides a control on a narrow viewport: it
//   stacks it, scrolls it sideways, or folds it into a disclosure.
import type { Action } from 'svelte/action';
import { goto, type BeforeNavigate } from '$app/navigation';
import { page } from '$app/state';
import { getGuild, getGuilds } from './api';
import type { IconName } from './components/ui/icons';
import { GUILD_BOUND_CHIPS, dropChips } from './search';
import type { Guild, GuildDetail } from './types';

/** The search param that names the selected guild. */
export const GUILD_PARAM = 'guild';

/** The id of the element page content scrolls in. */
export const SCROLLER_ID = 'shell-scroller';

/**
 * Screens about one channel or author, by path, and the index their destination falls
 * back to when the guild changes: what they show is not in the other guild.
 */
const GUILD_BOUND: [RegExp, string][] = [
	[/^\/browse\/[^/]+$/, '/browse'],
	[/^\/people\/[^/]+$/, '/people']
];

/** Search params that name something in one guild (a channel), dropped when the guild changes. */
const GUILD_BOUND_PARAMS = ['channel'];

/**
 * Screens whose params name things in one guild in their own way, by path, and how
 * switching guild rewrites those params so they name nothing from the old guild.
 */
const GUILD_BOUND_REWRITES: [RegExp, (params: URLSearchParams) => void][] = [
	// Search's `in:` and `from:` chips name a channel and an author.
	[
		/^\/search$/,
		(params) => {
			const q = params.get('q');
			if (q === null) return;
			const kept = dropChips(q, ...GUILD_BOUND_CHIPS);
			if (kept) params.set('q', kept);
			else params.delete('q');
		}
	]
];

export interface Destination {
	href: string;
	label: string;
	icon: IconName;
	/** Whether the destination owns `path`. */
	owns: (path: string) => boolean;
}

/**
 * The five destinations, in the sidebar's order, which is also ⌘1–5's.
 */
export const DESTINATIONS: Destination[] = [
	{ href: '/', label: 'Overview', icon: 'dashboard', owns: (p) => p === '/' },
	{ href: '/browse', label: 'Browse', icon: 'hash', owns: (p) => /^\/browse(\/|$)/.test(p) },
	{ href: '/media', label: 'Media', icon: 'images', owns: (p) => /^\/media(\/|$)/.test(p) },
	{ href: '/search', label: 'Search', icon: 'search', owns: (p) => /^\/search(\/|$)/.test(p) },
	{ href: '/people', label: 'People', icon: 'users', owns: (p) => /^\/people(\/|$)/.test(p) }
];

/** The viewport width below which the shell takes its narrow layout. */
export const NARROW_QUERY = '(max-width: 767px)';

const narrowQuery = typeof matchMedia === 'function' ? matchMedia(NARROW_QUERY) : null;
let narrow = $state(narrowQuery?.matches ?? false);
narrowQuery?.addEventListener('change', () => (narrow = narrowQuery.matches));

export const viewport = {
	/** Whether the viewport is narrower than 768px: a top bar, a sheet and a tab bar. */
	get narrow(): boolean {
		return narrow;
	}
};

let guilds = $state<Guild[]>([]);
let guildsError = $state('');

const selected = $derived.by((): Guild | null => {
	const id = page.url.searchParams.get(GUILD_PARAM);
	return guilds.find((g) => g.id === id) ?? guilds[0] ?? null;
});

export const shell = {
	/** Every archived guild, in the API's order. */
	get guilds(): Guild[] {
		return guilds;
	},
	/** The guild the screens show: the URL's `guild`, else the first. Null when nothing is archived. */
	get guild(): Guild | null {
		return selected;
	},
	/** Why the guilds could not be read, or ''. */
	get guildsError(): string {
		return guildsError;
	},
	/** The element page content scrolls in. */
	get scroller(): HTMLElement | undefined {
		return document.getElementById(SCROLLER_ID) ?? undefined;
	}
};

let stickyHeaders = 0;

/**
 * For a route's sticky header across the top of the scroll container: keeps the
 * container's scroll-padding-top at the header's height while it is mounted.
 */
export const stickyHeader: Action<HTMLElement> = (node) => {
	const scroller = shell.scroller;
	if (!scroller) return;
	// The header that set the padding last owns it; another may mount before this unmounts.
	const owner = String(++stickyHeaders);
	const observer = new ResizeObserver(() => {
		scroller.dataset.stickyHeader = owner;
		scroller.style.scrollPaddingTop = `${node.offsetHeight}px`;
	});
	observer.observe(node);
	return {
		destroy() {
			observer.disconnect();
			if (scroller.dataset.stickyHeader !== owner) return;
			delete scroller.dataset.stickyHeader;
			scroller.style.scrollPaddingTop = '';
		}
	};
};

/** Read the archived guilds; the root layout's load awaits this before any route renders. */
export async function loadGuilds(): Promise<void> {
	try {
		guilds = await getGuilds();
		guildsError = '';
	} catch (e) {
		guilds = [];
		guildsError = e instanceof Error ? e.message : 'Failed to load the archive';
	}
}

/** `href` with the current URL's `guild` param, when it has one and `href` does not. */
export function withGuild(href: string): string {
	const id = page.url.searchParams.get(GUILD_PARAM);
	const url = new URL(href, page.url.href);
	if (!id || url.searchParams.has(GUILD_PARAM)) return href;
	url.searchParams.set(GUILD_PARAM, id);
	return url.pathname + url.search + url.hash;
}

/**
 * Where switching to guild `id` from `from` goes: the same screen in that guild, or
 * its destination's index when the screen is about something only the old guild has.
 */
export function guildSwitchHref(id: string, from: string = page.url.href): string {
	const url = new URL(from);
	const bound = GUILD_BOUND.find(([pattern]) => pattern.test(url.pathname));
	if (bound) {
		url.pathname = bound[1];
		url.search = '';
	}
	for (const param of GUILD_BOUND_PARAMS) url.searchParams.delete(param);
	for (const [pattern, rewrite] of GUILD_BOUND_REWRITES) {
		if (pattern.test(url.pathname)) rewrite(url.searchParams);
	}
	url.searchParams.set(GUILD_PARAM, id);
	return url.pathname + url.search;
}

/**
 * A `beforeNavigate` callback that keeps the selected guild: a navigation inside the
 * portal to a URL without `guild` goes to that URL with the current one instead.
 */
export function carryGuild(navigation: BeforeNavigate): void {
	if (!['link', 'goto', 'form'].includes(navigation.type)) return;
	const to = navigation.to;
	if (!to?.route.id || to.url.origin !== page.url.origin) return;
	const id = page.url.searchParams.get(GUILD_PARAM);
	if (!id || to.url.searchParams.has(GUILD_PARAM)) return;
	navigation.cancel();
	const url = new URL(to.url);
	url.searchParams.set(GUILD_PARAM, id);
	void goto(url.pathname + url.search + url.hash);
}

/**
 * The selected guild's detail when it holds channel `channelId`. When another guild
 * holds it, that guild is selected instead, in place of this history entry, and this
 * resolves to null: the route remounts in that guild, so the caller stops there. When
 * no guild holds it, it is the selected guild's detail.
 */
export async function guildHolding(channelId: string): Promise<GuildDetail | null> {
	const current = selected;
	if (!current) return null;
	const detail = await getGuild(current.id);
	if (detail.channels.some((c) => c.id === channelId)) return detail;
	for (const other of guilds) {
		if (other.id === current.id) continue;
		const candidate = await getGuild(other.id);
		if (candidate.channels.some((c) => c.id === channelId)) {
			const url = new URL(page.url.href);
			url.searchParams.set(GUILD_PARAM, other.id);
			await goto(url.pathname + url.search, { replace: true });
			return null;
		}
	}
	return detail;
}

// ── The sidebar's rail ──────────────────────────────────────────────────────

const RAIL_KEY = 'wumpus.sidebar';

function storedRail(): boolean {
	try {
		return localStorage.getItem(RAIL_KEY) === 'rail';
	} catch {
		return false;
	}
}

let rail = $state(storedRail());

/** Whether the sidebar is collapsed to its icon rail; the choice is kept in localStorage. */
export const sidebar = {
	get rail(): boolean {
		return rail;
	},
	toggle(): void {
		rail = !rail;
		try {
			localStorage.setItem(RAIL_KEY, rail ? 'rail' : 'expanded');
		} catch {
			// Storage unavailable (private mode, blocked): the choice lasts this visit only
		}
	}
};

/** True on Apple platforms, whose shortcuts use Command where others use Control. */
export const APPLE = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

/** The sidebar toggle's keys as the keyboard labels them: Command-backslash, or Ctrl+\ off Apple. */
export const RAIL_SHORTCUT = APPLE ? '⌘\\' : 'Ctrl+\\';

/** The sidebar toggle's keys for aria-keyshortcuts. */
export const RAIL_KEYSHORTCUTS = APPLE ? 'Meta+Backslash' : 'Control+Backslash';

/** Whether `event` is the sidebar toggle: Command- or Control-backslash. */
export function isRailShortcut(event: KeyboardEvent): boolean {
	return (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key === '\\';
}
