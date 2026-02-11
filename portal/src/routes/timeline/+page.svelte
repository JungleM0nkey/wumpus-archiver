<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getGuilds, getMessages } from '$lib/api';
	import type { Guild, GuildDetail, Channel, Message } from '$lib/types';
	import { getGuild } from '$lib/api';
	import MessageCard from '$lib/components/MessageCard.svelte';
	import TimelineFeed from '$lib/components/TimelineFeed.svelte';
	import { ChannelType } from '$lib/types';

	let guild: GuildDetail | null = $state(null);
	let channels: Channel[] = $state([]);
	let messages: Message[] = $state([]);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let hasMore = $state(false);

	// Filters
	let selectedChannel: string | null = $state(null);
	let sortOrder: 'newest' | 'oldest' = $state('newest');

	// Derive channel param from URL
	let urlChannel = $derived(page.url.searchParams.get('channel'));

	onMount(async () => {
		try {
			const guilds = await getGuilds();
			if (guilds.length > 0) {
				guild = await getGuild(guilds[0].id);
				channels = guild.channels.filter(
					(ch) => ch.type === ChannelType.GUILD_TEXT || ch.type === ChannelType.GUILD_VOICE
				);

				if (urlChannel) {
					selectedChannel = urlChannel;
				} else if (channels.length > 0) {
					selectedChannel = channels[0].id;
				}

				if (selectedChannel) {
					await loadMessages();
				}
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load';
		} finally {
			loading = false;
		}
	});

	async function loadMessages() {
		if (!selectedChannel) return;
		loading = true;
		try {
			const res = await getMessages(selectedChannel, { limit: 100 });
			messages = res.messages;
			hasMore = res.has_more;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load messages';
		} finally {
			loading = false;
		}
	}

	async function loadMoreMessages() {
		if (!selectedChannel || !hasMore || loadingMore) return;
		loadingMore = true;
		try {
			const afterId = messages.length > 0 ? messages[messages.length - 1].id : undefined;
			const res = await getMessages(selectedChannel, { limit: 100, after: afterId });
			messages = [...messages, ...res.messages];
			hasMore = res.has_more;
		} catch (e) {
			console.error('Failed to load more:', e);
		} finally {
			loadingMore = false;
		}
	}

	async function selectChannel(channelId: string) {
		selectedChannel = channelId;
		messages = [];
		await loadMessages();
	}

	function getChannelIcon(type: number): string {
		switch (type) {
			case ChannelType.GUILD_VOICE: return '🔊';
			case ChannelType.GUILD_STAGE_VOICE: return '🎭';
			case ChannelType.GUILD_FORUM: return '💬';
			default: return '#';
		}
	}
</script>

<div class="timeline-page">
	<!-- Channel filter sidebar -->
	<aside class="filter-sidebar">
		<div class="sidebar-header">
			<h3 class="sidebar-title">Channels</h3>
			<span class="badge">{channels.length}</span>
		</div>

		<div class="channel-list">
			{#each channels as ch (ch.id)}
				<button
					class="channel-item"
					class:active={selectedChannel === ch.id}
					onclick={() => selectChannel(ch.id)}
				>
					<span class="channel-icon">{getChannelIcon(ch.type)}</span>
					<span class="channel-name truncate">{ch.name}</span>
					<span class="channel-count mono">{ch.message_count.toLocaleString()}</span>
				</button>
			{/each}
		</div>
	</aside>

	<!-- Main timeline area -->
	<div class="timeline-main">
		{#if selectedChannel}
			{@const ch = channels.find((c) => c.id === selectedChannel)}
			<header class="timeline-header">
				<div class="header-info">
					<h1 class="header-title">
						{#if ch}
							<span class="header-hash">{getChannelIcon(ch.type)}</span>
							{ch.name}
						{/if}
					</h1>
					{#if ch?.topic}
						<p class="header-topic">{ch.topic}</p>
					{/if}
				</div>
				<div class="header-meta">
					<span class="badge">{messages.length.toLocaleString()} loaded</span>
				</div>
			</header>
		{/if}

		<div class="timeline-content">
			{#if loading && messages.length === 0}
				<div class="center-state">
					<div class="spinner"></div>
					<span class="mono">Loading messages...</span>
				</div>
			{:else if error}
				<div class="center-state error">⚠ {error}</div>
			{:else if messages.length === 0}
				<div class="center-state">
					<span class="mono">No messages in this channel.</span>
				</div>
			{:else}
				<TimelineFeed {messages} />

				{#if hasMore}
					<div class="load-more">
						<button class="load-more-btn" onclick={loadMoreMessages} disabled={loadingMore}>
							{#if loadingMore}
								<div class="spinner-sm"></div>
								Loading...
							{:else}
								Load older messages
							{/if}
						</button>
					</div>
				{/if}
			{/if}
		</div>
	</div>
</div>

<style>
	.timeline-page {
		display: flex;
		height: 100%;
		overflow: hidden;
	}

	/* Sidebar */
	.filter-sidebar {
		width: var(--sidebar-width);
		flex-shrink: 0;
		background: var(--bg-surface);
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--sp-4) var(--sp-4);
		border-bottom: 1px solid var(--border);
	}

	.sidebar-title {
		font-size: 13px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-secondary);
	}

	.channel-list {
		flex: 1;
		overflow-y: auto;
		padding: var(--sp-2);
	}

	.channel-item {
		width: 100%;
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-2) var(--sp-3);
		border-radius: var(--radius-md);
		font-size: 14px;
		color: var(--text-secondary);
		transition: all 0.12s var(--ease-out);
		text-align: left;
	}

	.channel-item:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.channel-item.active {
		background: var(--accent-glow);
		color: var(--accent-text);
	}

	.channel-icon { flex-shrink: 0; font-size: 13px; opacity: 0.7; }
	.channel-name { flex: 1; min-width: 0; }
	.channel-count { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }

	/* Main */
	.timeline-main {
		flex: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		min-width: 0;
	}

	.timeline-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--sp-4) var(--sp-6);
		border-bottom: 1px solid var(--border);
		background: var(--bg-surface);
		flex-shrink: 0;
	}

	.header-title {
		font-size: 18px;
		font-weight: 600;
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.header-hash { color: var(--text-muted); font-size: 16px; }

	.header-topic {
		font-size: 13px;
		color: var(--text-muted);
		margin-top: var(--sp-1);
	}

	.timeline-content {
		flex: 1;
		overflow-y: auto;
		padding: var(--sp-6);
		max-width: var(--max-content);
		width: 100%;
		margin: 0 auto;
	}

	.center-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-16) 0;
		color: var(--text-muted);
	}

	.center-state.error { color: var(--error); }

	.load-more {
		display: flex;
		justify-content: center;
		padding: var(--sp-6) 0;
	}

	.load-more-btn {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-2) var(--sp-5);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		font-size: 14px;
		color: var(--text-secondary);
		transition: all 0.15s var(--ease-out);
	}

	.load-more-btn:hover:not(:disabled) {
		border-color: var(--border-strong);
		color: var(--text-primary);
	}

	.load-more-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.spinner {
		width: 20px; height: 20px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.spinner-sm {
		width: 14px; height: 14px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin { to { transform: rotate(360deg); } }
</style>
