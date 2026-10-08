<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';
	import { getGuilds, getGuild } from '#lib/api.ts';
	import { keepingPosition, newestPage, olderPage, scrollToBottom } from '#lib/reader.ts';
	import type { Message, Channel } from '#lib/types.ts';
	import TimelineFeed from '#lib/components/TimelineFeed.svelte';

	let { params }: PageProps = $props();
	const channelId = $derived(params.id);

	let channel: Channel | null = $state(null);
	let messages: Message[] = $state([]);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let hasMore = $state(false);
	let scroller: HTMLElement | undefined = $state();
	const limit = 50;

	onMount(async () => {
		await loadChannel();
		await loadMessages();
	});

	async function loadChannel() {
		try {
			const guilds = await getGuilds();
			if (guilds.length > 0) {
				const detail = await getGuild(guilds[0].id);
				channel = detail.channels.find(c => c.id === channelId) ?? null;
			}
		} catch (e) {
			console.error('Failed to load channel info:', e);
		}
	}

	async function loadMessages() {
		try {
			({ messages, hasMore } = await newestPage(channelId, limit));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load messages';
		} finally {
			loading = false;
		}
		await scrollToBottom(scroller);
	}

	async function loadOlder() {
		if (loadingMore || !hasMore || messages.length === 0) return;
		loadingMore = true;
		try {
			const older = await olderPage(channelId, messages[0], limit);
			await keepingPosition(scroller, () => {
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
	<header class="channel-header">
		<a href="/channels" class="back-link mono">← Channels</a>
		{#if channel}
			<div class="channel-title-row">
				<span class="hash">#</span>
				<h1>{channel.name}</h1>
			</div>
			{#if channel.topic}
				<p class="channel-topic">{channel.topic}</p>
			{/if}
			<div class="channel-meta mono">
				<span>{messages.length.toLocaleString()} messages loaded</span>
			</div>
			<a href="/channel/{channelId}/gallery" class="gallery-link">🖼 View Gallery</a>
		{:else if loading}
			<div class="channel-title-row">
				<h1 class="mono" style="color: var(--text-tertiary);">Loading...</h1>
			</div>
		{/if}
	</header>

	<div class="message-area" bind:this={scroller}>
		{#if loading}
			<div class="center-state">
				<div class="spinner"></div>
				<span class="mono">Loading messages...</span>
			</div>
		{:else if error}
			<div class="center-state error">⚠ {error}</div>
		{:else if messages.length === 0}
			<div class="center-state">
				<div class="empty-icon">∅</div>
				<span>No messages archived in this channel.</span>
			</div>
		{:else}
			<div class="feed-container">
				{#if hasMore}
					<div class="load-more">
						<button class="load-more-btn" onclick={loadOlder} disabled={loadingMore}>
							{#if loadingMore}
								<span class="spinner small"></span> Loading...
							{:else}
								Load older messages
							{/if}
						</button>
					</div>
				{:else}
					<div class="end-marker mono">
						— Beginning of archive —
					</div>
				{/if}

				<TimelineFeed {messages} />
			</div>
		{/if}
	</div>
</div>

<style>
	.channel-detail {
		height: 100%;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.channel-header {
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
		padding: var(--space-5) var(--space-6) var(--space-4);
		flex-shrink: 0;
	}

	.back-link {
		display: inline-block;
		font-size: 12px;
		color: var(--text-tertiary);
		text-decoration: none;
		margin-bottom: var(--space-3);
		transition: color var(--duration-micro);
	}

	.back-link:hover {
		color: var(--accent);
	}

	.channel-title-row {
		display: flex;
		align-items: baseline;
		gap: var(--space-2);
	}

	.hash {
		font-size: 28px;
		font-weight: 700;
		color: var(--text-tertiary);
	}

	.channel-title-row h1 {
		font-size: 24px;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	.channel-topic {
		font-size: 14px;
		color: var(--text-secondary);
		margin-top: var(--space-2);
		line-height: 1.5;
	}

	.channel-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 12px;
		color: var(--text-tertiary);
		margin-top: var(--space-3);
	}

	.sep { color: var(--text-tertiary); }

	.gallery-link {
		display: inline-block;
		margin-top: var(--space-3);
		font-size: 13px;
		color: var(--accent);
		text-decoration: none;
		font-weight: 500;
		transition: opacity var(--duration-micro);
	}

	.gallery-link:hover { opacity: 0.8; }

	/* The feed sits at the bottom while it is shorter than the area, as a chat does. */
	.message-area {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-6);
		display: flex;
		flex-direction: column;
	}

	.feed-container {
		width: 100%;
		max-width: var(--size-reader-max);
		margin: auto auto 0;
	}

	.load-more {
		display: flex;
		justify-content: center;
		padding: var(--space-6) 0;
	}

	.load-more-btn {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--text-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		padding: var(--space-2) var(--space-5);
		cursor: pointer;
		transition: all var(--duration-micro) var(--ease-out-quint);
	}

	.load-more-btn:hover:not(:disabled) {
		border-color: var(--accent);
		color: var(--accent);
	}

	.load-more-btn:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.end-marker {
		text-align: center;
		font-size: 12px;
		color: var(--text-tertiary);
		padding: var(--space-8) 0;
	}

	.center-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-16) 0;
		color: var(--text-secondary);
	}

	.center-state.error { color: var(--danger); }

	.empty-icon {
		font-size: 48px;
		color: var(--text-tertiary);
	}

	.spinner {
		width: 20px; height: 20px;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.spinner.small {
		width: 14px; height: 14px;
	}

	@keyframes spin { to { transform: rotate(360deg); } }
</style>
