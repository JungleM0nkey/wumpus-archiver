<!--
	Browse's feed: loaded messages, oldest first, under a date pill per day that sticks
	below the reader's header (`--reader-header-height`) while its day is in view, and
	grouped by author (feed.ts). Rows do not animate in: older pages are added above what
	the reader is looking at.

	The rows' images, GIFs and videos open in the one Lightbox, which steps through the
	media of every loaded message in feed order, and takes in more as pages load. Esc
	gives the focus back to the attachment it opened from. "Open in conversation" there
	stays in the feed, where the message already is: it closes on that message's
	attachment, scrolling to it if it is out of view.
-->
<script lang="ts">
	import { feedDays, feedMedia } from '#lib/feed.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { Attachment, GalleryAttachment, Message, MessageReference } from '#lib/types.ts';
	import Lightbox from './Lightbox.svelte';
	import MessageRow from './MessageRow.svelte';

	let {
		messages,
		highlight = null,
		flash = null,
		focusable = null,
		busy = false,
		channelName = null,
		onreference,
		onnearend
	}: {
		messages: Message[];
		/** The id of the message to mark, the one a link opened the reader on. */
		highlight?: string | null;
		/** The id of the message to mark briefly, one a reply was followed to. */
		flash?: string | null;
		/** The id of the row Tab reaches in the feed's roving focus; null for none. */
		focusable?: string | null;
		/** Whether a page is loading into the feed. */
		busy?: boolean;
		/** The channel's name, which the Lightbox shows beside the author. */
		channelName?: string | null;
		onreference?: (reference: MessageReference, event: MouseEvent) => void;
		/** The Lightbox stepped near the newest loaded attachment: a feed that pages loads newer. */
		onnearend?: () => void;
	} = $props();

	const days = $derived(feedDays(messages));
	const media = $derived(feedMedia(messages, channelName));

	let feed: HTMLElement | undefined = $state();
	let lightbox: Lightbox | undefined = $state();

	function open(attachment: Attachment, tile: HTMLElement) {
		const item = media.find((a) => a.id === attachment.id);
		if (item) void lightbox?.open(item, tile);
	}

	/** "Open in conversation": close on the attachment in its row, rather than reload the feed. */
	function inConversation(attachment: GalleryAttachment, event: MouseEvent) {
		if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
		const tile = feed?.querySelector<HTMLElement>(
			`.attachment-media[data-attachment-id="${CSS.escape(attachment.id)}"]`
		);
		if (!tile) return; // The link opens the message in Browse.
		event.preventDefault();
		if (!inView(tile)) tile.scrollIntoView({ block: 'center' });
		void lightbox?.close(tile);
	}

	/** Whether all of `el` shows in the scroll container, below the reader's sticky header. */
	function inView(el: HTMLElement): boolean {
		const scroller = shell.scroller;
		if (!scroller || !feed) return false;
		const header = parseFloat(getComputedStyle(feed).getPropertyValue('--reader-header-height')) || 0;
		const bounds = scroller.getBoundingClientRect();
		const box = el.getBoundingClientRect();
		return box.top >= bounds.top + header && box.bottom <= bounds.bottom;
	}
</script>

<div class="feed" role="feed" aria-label="Messages" aria-busy={busy} bind:this={feed}>
	{#each days as day (day.key)}
		<div class="day" data-day={day.key}>
			<div class="divider" aria-hidden="true">
				<span class="pill mono">{day.label}</span>
			</div>
			{#each day.rows as row (row.message.id)}
				<MessageRow
					message={row.message}
					continuation={row.continuation}
					highlighted={row.message.id === highlight}
					flash={row.message.id === flash}
					tabindex={row.message.id === focusable ? 0 : -1}
					{onreference}
					onopen={open}
				/>
			{/each}
		</div>
	{/each}
</div>

<Lightbox bind:this={lightbox} attachments={media} {onnearend} onconversation={inConversation} />

<style>
	.feed {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	/* The line across the top of the day, which the pill sits on until it sticks. */
	.day {
		position: relative;
	}

	.day::before {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		top: calc(var(--space-2) + 10px);
		height: 1px;
		background: var(--border-subtle);
	}

	/* The pill alone sticks, below the reader's header, while its day is in view. */
	.divider {
		position: sticky;
		top: calc(var(--reader-header-height, var(--size-topbar)) + var(--space-2));
		z-index: 1;
		display: flex;
		justify-content: center;
		margin: var(--space-2) 0 var(--space-1);
		pointer-events: none;
	}

	.pill {
		height: 20px;
		display: inline-flex;
		align-items: center;
		padding: 0 var(--space-3);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-full);
		background: var(--bg-raised);
		font: var(--type-mono-sm);
		color: var(--text-secondary);
		white-space: nowrap;
	}
</style>
