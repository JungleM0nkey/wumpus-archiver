<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';
	import { guildHolding, shell, stickyHeader } from '#lib/shell.svelte.ts';
	import { keepingPosition, newestPage, olderPage, scrollToBottom } from '#lib/reader.ts';
	import type { Message, Channel } from '#lib/types.ts';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import MessageSkeleton from '#lib/components/MessageSkeleton.svelte';
	import TimelineFeed from '#lib/components/TimelineFeed.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	let { params }: PageProps = $props();
	const channelId = $derived(params.id);

	let channel: Channel | null = $state(null);
	let messages: Message[] = $state([]);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let hasMore = $state(false);
	const limit = 50;

	onMount(async () => {
		if (await loadChannel()) await loadMessages();
	});

	/** Read the channel from its guild; false when the shell moves to the guild that holds it. */
	async function loadChannel(): Promise<boolean> {
		try {
			const detail = await guildHolding(channelId);
			if (!detail && shell.guild) return false;
			channel = detail?.channels.find((c) => c.id === channelId) ?? null;
		} catch (e) {
			console.error('Failed to load channel info:', e);
		}
		return true;
	}

	async function loadMessages() {
		try {
			({ messages, hasMore } = await newestPage(channelId, limit));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load messages';
		} finally {
			loading = false;
		}
		await scrollToBottom(shell.scroller);
	}

	async function loadOlder() {
		if (loadingMore || !hasMore || messages.length === 0) return;
		loadingMore = true;
		try {
			const older = await olderPage(channelId, messages[0], limit);
			await keepingPosition(shell.scroller, () => {
				messages = [...older.messages, ...messages];
				hasMore = older.hasMore;
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load more';
		} finally {
			loadingMore = false;
		}
	}
</script>

<div class="channel-detail">
	<header class="channel-header" use:stickyHeader>
		<a href="/channels" class="back-link"><Icon name="arrow-left" size={14} /> Channels</a>
		{#if channel}
			<div class="channel-title-row">
				<Icon name="hash" size={20} />
				<h1>{channel.name}</h1>
			</div>
			{#if channel.topic}
				<p class="channel-topic">{channel.topic}</p>
			{/if}
			<div class="channel-meta">
				<span class="mono">{messages.length.toLocaleString()} messages loaded</span>
				<a href="/channel/{channelId}/gallery" class="gallery-link">
					<Icon name="images" size={14} /> View Gallery
				</a>
			</div>
		{:else if loading}
			<div class="title-skeleton" aria-hidden="true">
				<Skeleton width="180px" height="24px" />
			</div>
		{/if}
	</header>

	<div class="message-area">
		{#if loading}
			<div class="feed-container"><MessageSkeleton /></div>
		{:else if error}
			<div class="state"><Alert tone="danger" title="Messages could not be loaded">{error}</Alert></div>
		{:else if messages.length === 0}
			<div class="state"><EmptyState icon="inbox" title="No messages archived in this channel." /></div>
		{:else}
			<div class="feed-container">
				{#if hasMore}
					<LoadMore loading={loadingMore} onclick={loadOlder}>Load older messages</LoadMore>
				{:else}
					<div class="end-marker mono">Beginning of archive</div>
				{/if}

				<TimelineFeed {messages} />
			</div>
		{/if}
	</div>
</div>

<style>
	/* At least the shell's height, so the feed can sit at its bottom. */
	.channel-detail {
		min-height: 100%;
		display: flex;
		flex-direction: column;
	}

	.channel-header {
		position: sticky;
		top: 0;
		z-index: 2;
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
		padding: var(--space-4) var(--space-6);
		flex-shrink: 0;
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-label-sm);
		color: var(--text-tertiary);
		margin-bottom: var(--space-2);
	}

	.back-link:hover {
		color: var(--text-primary);
	}

	.channel-title-row {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		color: var(--text-tertiary);
	}

	.channel-title-row h1 {
		font: var(--type-heading-lg);
		color: var(--text-primary);
	}

	.title-skeleton {
		padding: var(--space-1) 0;
	}

	.channel-topic {
		font: var(--type-body-md);
		color: var(--text-secondary);
		margin-top: var(--space-1);
	}

	.channel-meta {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		margin-top: var(--space-2);
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.gallery-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-label-sm);
	}

	/* The feed sits at the bottom while it is shorter than the area, as a chat does. */
	.message-area {
		flex: 1;
		padding: var(--space-6);
		display: flex;
		flex-direction: column;
	}

	.feed-container {
		width: 100%;
		max-width: var(--size-reader-max);
		margin: auto auto 0;
	}

	.state {
		width: 100%;
		max-width: var(--size-reader-max);
		margin: auto;
	}

	.end-marker {
		text-align: center;
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		padding: var(--space-8) 0;
	}
</style>
