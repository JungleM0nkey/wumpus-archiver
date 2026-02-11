<script lang="ts">
	import type { Message } from '$lib/types';
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
	<h2 class="feed-title serif">{title}</h2>
{/if}

<div class="timeline-feed">
	{#each grouped as group, gi (group.date)}
		<div class="date-group fade-in" style="animation-delay: {gi * 50}ms">
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
		font-size: 22px;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: var(--sp-6);
	}

	.timeline-feed {
		display: flex;
		flex-direction: column;
		gap: var(--sp-6);
	}

	.date-group {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
	}

	.date-divider {
		display: flex;
		align-items: center;
		gap: var(--sp-4);
		padding: var(--sp-1) 0;
	}

	.date-line {
		flex: 1;
		height: 1px;
		background: var(--border);
	}

	.date-label {
		font-size: 12px;
		color: var(--text-muted);
		white-space: nowrap;
		letter-spacing: 0.02em;
	}

	.messages-group {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
	}
</style>
