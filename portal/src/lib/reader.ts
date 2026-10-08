// The channel reader's paging: it opens at a channel's newest messages and pages back
// in time with `before` from the oldest loaded message (ADR 0003). Opened on one
// message, it reads the page `around` it and pages both ways, newer with `after`. The
// API returns a page newest-first; the reader shows messages oldest at the top, newest
// at the bottom.

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

/** Loaded messages, oldest first, around one message, and what remains on either side. */
export interface AnchoredPage {
	messages: Message[];
	hasOlder: boolean;
	hasNewer: boolean;
}

/**
 * The page holding message `messageId` with its neighbours on both sides (`around`).
 * When the channel has no such message it is the channel's newest page.
 */
export async function pageAround(
	channelId: string,
	messageId: string,
	limit: number
): Promise<AnchoredPage> {
	const res = await getMessages(channelId, { limit, around: messageId });
	return {
		messages: [...res.messages].reverse(),
		hasOlder: res.has_more,
		hasNewer: res.has_newer ?? false
	};
}

/** The page adjacent to `newest` on the newer side; `hasMore` says whether newer ones remain. */
export async function newerPage(
	channelId: string,
	newest: Message,
	limit: number
): Promise<ReaderPage> {
	const res = await getMessages(channelId, { limit, after: newest.id });
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
