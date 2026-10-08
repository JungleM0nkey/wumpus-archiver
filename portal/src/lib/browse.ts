// What Browse's layout shares with its pages: the selected guild's detail, with its
// channels, read once while the channel pane stays mounted from channel to channel.

import { createContext } from 'svelte';
import type { GuildDetail } from './types';

export interface BrowseGuild {
	/** The guild's detail once read; null before, or when it could not be read. */
	readonly detail: GuildDetail | null;
	/**
	 * Resolves once the detail is read (or could not be): true, or false when the shell
	 * is moving to the guild that holds the channel the URL names, and the route remounts.
	 */
	readonly ready: Promise<boolean>;
	/**
	 * The channel the layout already looked for in every guild (`guildHolding`) when it
	 * mounted, so the page need not look again; null when the URL named none.
	 */
	readonly checked: string | null;
}

export const [getBrowseGuild, setBrowseGuild] = createContext<BrowseGuild>();
