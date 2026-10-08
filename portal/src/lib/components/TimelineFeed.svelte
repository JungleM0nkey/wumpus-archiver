<script lang="ts">
	import type { Message } from '#lib/types.ts';
	import MessageCard from './MessageCard.svelte';

	let {
		messages,
		title = '',
	}: {
		messages: Message[];
		title?: string;
	} = $props();

	// Group messages by date
	let grouped = $derived.by(() => {
		const groups: { date: string; messages: Message[] }[] = [];
		let currentDate = '';

		for (const msg of messages) {
			const d = new Date(msg.created_at);
			const dateKey = d.toLocaleDateString('en-US', {
				weekday: 'long',
				month: 'long',
				day: 'numeric',
				year: 'numeric',
			});

			if (dateKey !== currentDate) {
				currentDate = dateKey;
				groups.push({ date: dateKey, messages: [] });
			}
			groups[groups.length - 1].messages.push(msg);
		}
		return groups;
	});
</script>

{#if title}
	<h2 class="feed-title">{title}</h2>
{/if}

<!-- Groups do not animate in: older pages are added above what the reader is looking at. -->
<div class="timeline-feed">
	{#each grouped as group (group.date)}
		<div class="date-group">
			<div class="date-divider">
				<div class="date-line"></div>
				<span class="date-label mono">{group.date}</span>
				<div class="date-line"></div>
			</div>

			<div class="messages-group">
				{#each group.messages as msg (msg.id)}
					<MessageCard message={msg} />
				{/each}
			</div>
		</div>
	{/each}
</div>

<style>
	.feed-title {
		font: var(--type-heading-lg);
		color: var(--text-primary);
		margin-bottom: var(--space-6);
	}

	.timeline-feed {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.date-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.date-divider {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-1) 0;
	}

	.date-line {
		flex: 1;
		height: 1px;
		background: var(--border-subtle);
	}

	.date-label {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	.messages-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}
</style>
