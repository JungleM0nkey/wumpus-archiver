// How Browse's reader lays out its feed (audit #16): the messages of each day under a
// date divider, and consecutive messages by one author under one header while they
// follow it within GROUP_WINDOW_MS. The rows after a header are its continuations,
// which show no avatar, name or time of their own. The feed's media open in the
// Lightbox, which steps through them in feed order (feedMedia).

import { isMedia } from './media';
import type { GalleryAttachment, Message } from './types';

/** How long after a group's header the same author's messages still join the group. */
export const GROUP_WINDOW_MS = 5 * 60 * 1000;

/** One message in the feed: a header, or a continuation of the header above it. */
export interface FeedRow {
	message: Message;
	continuation: boolean;
}

/** One day of the feed, oldest first like its rows. */
export interface FeedDay {
	/** The day as YYYY-MM-DD, in the viewer's time zone. */
	key: string;
	/** The day as the divider shows it, e.g. "Monday, May 20, 2024". */
	label: string;
	rows: FeedRow[];
}

/** The day of `date` as YYYY-MM-DD, in the viewer's time zone. */
function dayKey(date: Date): string {
	const pad = (n: number) => String(n).padStart(2, '0');
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Whether `message` joins the group that `head` starts. */
export function joinsGroup(head: Message, message: Message): boolean {
	if (!message.author_id || message.author_id !== head.author_id) return false;
	// A reply shows what it answers above its own header.
	if (message.reference_id) return false;
	const gap = Date.parse(message.created_at) - Date.parse(head.created_at);
	return gap >= 0 && gap <= GROUP_WINDOW_MS;
}

/** `messages`, oldest first, as days of grouped rows. */
export function feedDays(messages: Message[]): FeedDay[] {
	const days: FeedDay[] = [];
	let head: Message | null = null;
	for (const message of messages) {
		const date = new Date(message.created_at);
		const key = dayKey(date);
		let day = days[days.length - 1];
		if (!day || day.key !== key) {
			day = {
				key,
				label: date.toLocaleDateString('en-US', {
					weekday: 'long',
					month: 'long',
					day: 'numeric',
					year: 'numeric'
				}),
				rows: []
			};
			days.push(day);
			head = null;
		}
		const continuation = head !== null && joinsGroup(head, message);
		if (!continuation) head = message;
		day.rows.push({ message, continuation });
	}
	return days;
}

/** The month a message was posted in, YYYY-MM, as the archive's activity counts it (UTC). */
export function messageMonth(message: Message): string {
	return message.created_at.slice(0, 7);
}

/**
 * The media attachments (images, GIFs, videos) of `messages`, in feed order, as the
 * Lightbox shows them: each with its message's author and time, in channel
 * `channelName`.
 */
export function feedMedia(messages: Message[], channelName: string | null = null): GalleryAttachment[] {
	return messages.flatMap((message) =>
		message.attachments.filter(isMedia).map((attachment) => ({
			...attachment,
			created_at: message.created_at,
			author_name: message.author?.display_name || message.author?.username || null,
			author_avatar_url: message.author?.avatar_url ?? null,
			channel_id: message.channel_id,
			channel_name: channelName
		}))
	);
}
