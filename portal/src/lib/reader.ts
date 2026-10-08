// The channel reader's paging: it opens at a channel's newest messages and pages back
// in time with `before` from the oldest loaded message (ADR 0003). The API returns a
// page newest-first; the reader shows messages oldest at the top, newest at the bottom.

import { tick } from 'svelte';
import { getMessages } from './api';
import type { Message } from './types';

/** Loaded messages, oldest first, and whether older ones remain in the channel. */
export interface ReaderPage {
	messages: Message[];
	hasMore: boolean;
}

/** The channel's newest page. */
export async function newestPage(channelId: string, limit: number): Promise<ReaderPage> {
	const res = await getMessages(channelId, { limit });
	return { messages: [...res.messages].reverse(), hasMore: res.has_more };
}

/** The page adjacent to `oldest` on the older side. */
export async function olderPage(
	channelId: string,
	oldest: Message,
	limit: number
): Promise<ReaderPage> {
	const res = await getMessages(channelId, { limit, before: oldest.id });
	return { messages: [...res.messages].reverse(), hasMore: res.has_more };
}

/** Once the DOM has updated, scroll `scroller` to its bottom, where the newest messages are. */
export async function scrollToBottom(scroller: HTMLElement | undefined): Promise<void> {
	await tick();
	if (scroller) scroller.scrollTop = scroller.scrollHeight;
}

/**
 * Run `prepend`, which adds content above what is in view, and keep that view in place:
 * the scroller keeps its distance from the bottom, so everything already loaded stays
 * where it was on screen. The feed must sit at the bottom of the scroller while it is
 * shorter than it, as a chat does, for this to hold before the feed overflows.
 */
export async function keepingPosition(
	scroller: HTMLElement | undefined,
	prepend: () => void
): Promise<void> {
	const fromBottom = scroller ? scroller.scrollHeight - scroller.scrollTop : 0;
	prepend();
	await tick();
	if (scroller) scroller.scrollTop = scroller.scrollHeight - fromBottom;
}
