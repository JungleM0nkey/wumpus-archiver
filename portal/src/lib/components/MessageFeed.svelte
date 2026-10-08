<!--
	Browse's feed: loaded messages, oldest first, under a date pill per day that sticks
	below the reader's header (`--reader-header-height`) while its day is in view, and
	grouped by author (feed.ts). Rows do not animate in: older pages are added above what
	the reader is looking at.
-->
<script lang="ts">
	import { feedDays } from '#lib/feed.ts';
	import type { Message, MessageReference } from '#lib/types.ts';
	import MessageRow from './MessageRow.svelte';

	let {
		messages,
		highlight = null,
		flash = null,
		focusable = null,
		busy = false,
		onreference
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
		onreference?: (reference: MessageReference, event: MouseEvent) => void;
	} = $props();

	const days = $derived(feedDays(messages));
</script>

<div class="feed" role="feed" aria-label="Messages" aria-busy={busy}>
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
				/>
			{/each}
		</div>
	{/each}
</div>

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
