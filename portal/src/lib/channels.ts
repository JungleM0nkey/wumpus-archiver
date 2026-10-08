// The channels Browse lists, and how its channel pane groups them: under their
// categories as Discord shows them, with each thread after the channel it belongs to.

import type { IconName } from './components/ui/icons.ts';
import { ChannelType, type Channel } from './types.ts';

/** Channels that are not read as a feed of messages: voice channels and categories. */
const UNREAD_TYPES: number[] = [
	ChannelType.GUILD_VOICE,
	ChannelType.GUILD_STAGE_VOICE,
	ChannelType.GUILD_CATEGORY
];

const THREAD_TYPES: number[] = [ChannelType.PUBLIC_THREAD, ChannelType.PRIVATE_THREAD];

/** Whether Browse lists `channel`: anything but a voice channel or a category. */
export function isReadable(channel: Channel): boolean {
	return !UNREAD_TYPES.includes(channel.type);
}

/** Whether `channel` is a thread. */
export function isThread(channel: Channel): boolean {
	return THREAD_TYPES.includes(channel.type);
}

/** The icon for a channel of `type`. */
export function channelIcon(type: number): IconName {
	switch (type) {
		case ChannelType.GUILD_FORUM:
			return 'forum';
		case ChannelType.PUBLIC_THREAD:
		case ChannelType.PRIVATE_THREAD:
			return 'message';
		default:
			return 'hash';
	}
}

/** A category of the channel pane and the channels under it; `category` is null for those in none. */
export interface ChannelGroup {
	category: Channel | null;
	channels: Channel[];
}

function byPosition(a: Channel, b: Channel): number {
	return a.position - b.position || a.name.localeCompare(b.name) || a.id.localeCompare(b.id);
}

/**
 * The readable channels of a guild in the pane's order: those in no category first, then
 * each category by position, each listing its channels by position with every thread
 * after its parent channel. A category with nothing readable is left out.
 */
export function channelGroups(channels: Channel[]): ChannelGroup[] {
	const categories = channels.filter((c) => c.type === ChannelType.GUILD_CATEGORY).sort(byPosition);
	const readable = channels.filter(isReadable);
	const threads = readable.filter(isThread).sort(byPosition);
	const listed = readable.filter((c) => !isThread(c)).sort(byPosition);
	const listedIds = new Set(listed.map((c) => c.id));

	const withThreads = (parents: Channel[]): Channel[] =>
		parents.flatMap((parent) => [parent, ...threads.filter((t) => t.parent_id === parent.id)]);

	const categoryIds = new Set(categories.map((c) => c.id));
	const uncategorized = withThreads(
		listed.filter((c) => !c.parent_id || !categoryIds.has(c.parent_id))
	);
	// A thread whose channel is not listed has nowhere else to go.
	uncategorized.push(...threads.filter((t) => !t.parent_id || !listedIds.has(t.parent_id)));

	const groups: ChannelGroup[] = [];
	if (uncategorized.length > 0) groups.push({ category: null, channels: uncategorized });
	for (const category of categories) {
		const inside = withThreads(listed.filter((c) => c.parent_id === category.id));
		if (inside.length > 0) groups.push({ category, channels: inside });
	}
	return groups;
}

/** `groups` with only the channels whose name contains `query`, ignoring case. */
export function filterGroups(groups: ChannelGroup[], query: string): ChannelGroup[] {
	const needle = query.trim().toLocaleLowerCase();
	if (!needle) return groups;
	return groups
		.map((g) => ({
			category: g.category,
			channels: g.channels.filter((c) => c.name.toLocaleLowerCase().includes(needle))
		}))
		.filter((g) => g.channels.length > 0);
}

/**
 * The channel Browse opens on when none is named: the one with the most messages, or
 * the first in the pane when none has any. Null when the guild has nothing readable.
 */
export function openingChannel(channels: Channel[]): Channel | null {
	const ordered = channelGroups(channels).flatMap((g) => g.channels);
	let best: Channel | null = ordered[0] ?? null;
	for (const channel of ordered) {
		if (best && channel.message_count > best.message_count) best = channel;
	}
	return best;
}
