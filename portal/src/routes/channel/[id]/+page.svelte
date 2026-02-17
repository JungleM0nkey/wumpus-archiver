<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { getMessages, getGuilds, getGuild } from '$lib/api';
	import type { Message, Channel } from '$lib/types';
	import TimelineFeed from '$lib/components/TimelineFeed.svelte';
	import ChannelGallery from '$lib/components/ChannelGallery.svelte';

	type Tab = 'messages' | 'gallery';

	const channelId = $derived(page.params.id);

	let channel: Channel | null = $state(null);
	let guildId: string | null = $state(null);
	let messages: Message[] = $state([]);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let hasMore = $state(true);
	const limit = 50;

	// Tab state — read initial value from URL
	let activeTab: Tab = $state('messages');

	onMount(async () => {
		const urlTab = page.url.searchParams.get('tab');
		if (urlTab === 'gallery') {
			activeTab = 'gallery';
		}

		await loadChannel();
		await loadMessages();
	});

	function switchTab(tab: Tab) {
		if (activeTab === tab) return;
		activeTab = tab;
		const url = new URL(page.url);
		if (tab === 'messages') {
			url.searchParams.delete('tab');
		} else {
			url.searchParams.set('tab', tab);
		}
		goto(url.toString(), { replaceState: true, noScroll: true });
	}

	async function loadChannel() {
		try {
			const guilds = await getGuilds();
			if (guilds.length > 0) {
				const detail = await getGuild(guilds[0].id);
				guildId = detail.id;
				channel = detail.channels.find(c => c.id === channelId) ?? null;
			}
		} catch (e) {
			console.error('Failed to load channel info:', e);
		}
	}

	async function loadMessages() {
		try {
			const res = await getMessages(channelId, { limit });
			messages = res.messages;
			hasMore = res.has_more;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load messages';
		} finally {
			loading = false;
		}
	}

	async function loadMore() {
		if (loadingMore || !hasMore) return;
		loadingMore = true;
		try {
			const afterId = messages.length > 0 ? messages[messages.length - 1].id : undefined;
			const res = await getMessages(channelId, { limit, after: afterId });
			messages = [...messages, ...res.messages];
			hasMore = res.has_more;
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
		{:else if loading}
			<div class="channel-title-row">
				<h1 class="mono" style="color: var(--text-muted);">Loading...</h1>
			</div>
		{/if}

		<!-- Tab bar -->
		<div class="tab-bar" role="tablist">
			<button
				class="tab-btn"
				class:active={activeTab === 'messages'}
				onclick={() => switchTab('messages')}
				role="tab"
				aria-selected={activeTab === 'messages'}
			>
				<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
					<path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v8a1 1 0 01-1 1H5l-3 3V3z"/>
				</svg>
				Messages
			</button>
			<button
				class="tab-btn"
				class:active={activeTab === 'gallery'}
				onclick={() => switchTab('gallery')}
				role="tab"
				aria-selected={activeTab === 'gallery'}
			>
				<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
					<rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/>
					<rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/>
				</svg>
				Gallery
			</button>
		</div>
	</header>

	<div class="content-area">
		{#if activeTab === 'messages'}
			<div class="message-area">
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
						<TimelineFeed {messages} />

						{#if hasMore}
							<div class="load-more">
								<button class="load-more-btn" onclick={loadMore} disabled={loadingMore}>
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
					</div>
				{/if}
			</div>
		{:else if activeTab === 'gallery' && guildId}
			<ChannelGallery {channelId} {guildId} />
		{:else if activeTab === 'gallery'}
			<div class="message-area">
				<div class="center-state">
					<div class="spinner"></div>
					<span class="mono">Loading gallery...</span>
				</div>
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
		border-bottom: 1px solid var(--border);
		padding: var(--sp-5) var(--sp-6) 0;
		flex-shrink: 0;
	}

	.back-link {
		display: inline-block;
		font-size: 12px;
		color: var(--text-muted);
		text-decoration: none;
		margin-bottom: var(--sp-3);
		transition: color 0.12s;
	}

	.back-link:hover {
		color: var(--accent);
	}

	.channel-title-row {
		display: flex;
		align-items: baseline;
		gap: var(--sp-2);
	}

	.hash {
		font-size: 28px;
		font-weight: 700;
		color: var(--text-faint);
	}

	.channel-title-row h1 {
		font-size: 24px;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	.channel-topic {
		font-size: 14px;
		color: var(--text-secondary);
		margin-top: var(--sp-2);
		line-height: 1.5;
	}

	.channel-meta {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		font-size: 12px;
		color: var(--text-muted);
		margin-top: var(--sp-3);
	}

	/* ── Tab bar ── */
	.tab-bar {
		display: flex;
		gap: var(--sp-1);
		margin-top: var(--sp-4);
	}

	.tab-btn {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: var(--sp-2) var(--sp-4);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-secondary);
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		cursor: pointer;
		transition: all 0.15s var(--ease-out);
		margin-bottom: -1px;
	}

	.tab-btn:hover {
		color: var(--text-primary);
	}

	.tab-btn.active {
		color: var(--accent);
		border-bottom-color: var(--accent);
	}

	.tab-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	/* ── Content area ── */
	.content-area {
		flex: 1;
		overflow: hidden;
		display: flex;
		flex-direction: column;
	}

	.message-area {
		flex: 1;
		overflow-y: auto;
		padding: var(--sp-6);
	}

	.feed-container {
		max-width: var(--max-content);
		margin: 0 auto;
	}

	.load-more {
		display: flex;
		justify-content: center;
		padding: var(--sp-6) 0;
	}

	.load-more-btn {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--text-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		padding: var(--sp-2) var(--sp-5);
		cursor: pointer;
		transition: all 0.15s var(--ease-out);
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
		color: var(--text-faint);
		padding: var(--sp-8) 0;
	}

	.center-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-16) 0;
		color: var(--text-secondary);
	}

	.center-state.error { color: var(--error); }

	.empty-icon {
		font-size: 48px;
		color: var(--text-faint);
	}

	.spinner {
		width: 20px; height: 20px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.spinner.small {
		width: 14px; height: 14px;
	}

	@keyframes spin { to { transform: rotate(360deg); } }

	/* ── Responsive ── */
	@media (max-width: 768px) {
		.channel-header {
			padding: var(--sp-4) var(--sp-4) 0;
		}
		.message-area {
			padding: var(--sp-4);
		}
	}
</style>
