<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getGuilds } from '#lib/api.ts';
	import { keepingPosition, newestPage, olderPage, scrollToBottom } from '#lib/reader.ts';
	import type { GuildDetail, Channel, Message } from '#lib/types.ts';
	import { getGuild } from '#lib/api.ts';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import MessageSkeleton from '#lib/components/MessageSkeleton.svelte';
	import TimelineFeed from '#lib/components/TimelineFeed.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import type { IconName } from '#lib/components/ui/icons.ts';
	import { ChannelType } from '#lib/types.ts';

	let guild: GuildDetail | null = $state(null);
	let channels: Channel[] = $state([]);
	let messages: Message[] = $state([]);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let hasMore = $state(false);
	let scroller: HTMLElement | undefined = $state();
	const limit = 100;

	// Filters
	let selectedChannel: string | null = $state(null);

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
			({ messages, hasMore } = await newestPage(selectedChannel, limit));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load messages';
		} finally {
			loading = false;
		}
		await scrollToBottom(scroller);
	}

	async function loadOlderMessages() {
		if (!selectedChannel || !hasMore || loadingMore || messages.length === 0) return;
		loadingMore = true;
		try {
			const older = await olderPage(selectedChannel, messages[0], limit);
			await keepingPosition(scroller, () => {
				messages = [...older.messages, ...messages];
				hasMore = older.hasMore;
			});
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

	function channelIcon(type: number): IconName {
		switch (type) {
			case ChannelType.GUILD_VOICE: return 'voice';
			case ChannelType.GUILD_STAGE_VOICE: return 'stage';
			case ChannelType.GUILD_FORUM: return 'forum';
			default: return 'hash';
		}
	}
</script>

<div class="timeline-page">
	<!-- Channel filter sidebar -->
	<aside class="filter-sidebar">
		<div class="sidebar-header">
			<h2 class="sidebar-title">Channels</h2>
			<Badge mono>{channels.length}</Badge>
		</div>

		<div class="channel-list">
			{#each channels as ch (ch.id)}
				<button
					class="channel-item"
					class:active={selectedChannel === ch.id}
					aria-pressed={selectedChannel === ch.id}
					onclick={() => selectChannel(ch.id)}
				>
					<Icon name={channelIcon(ch.type)} />
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
							<Icon name={channelIcon(ch.type)} size={18} />
							{ch.name}
						{/if}
					</h1>
					{#if ch?.topic}
						<p class="header-topic">{ch.topic}</p>
					{/if}
				</div>
				<div class="header-meta">
					<Badge mono>{messages.length.toLocaleString()} loaded</Badge>
				</div>
			</header>
		{/if}

		<div class="timeline-content" bind:this={scroller}>
			{#if loading && messages.length === 0}
				<div class="feed"><MessageSkeleton /></div>
			{:else if error}
				<div class="state"><Alert tone="danger" title="Messages could not be loaded">{error}</Alert></div>
			{:else if messages.length === 0}
				<div class="state"><EmptyState icon="inbox" title="No messages in this channel." /></div>
			{:else}
				<div class="feed">
					{#if hasMore}
						<LoadMore loading={loadingMore} onclick={loadOlderMessages}>Load older messages</LoadMore>
					{/if}

					<TimelineFeed {messages} />
				</div>
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
		width: var(--size-sidebar);
		flex-shrink: 0;
		background: var(--bg-surface);
		border-right: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
	}

	.sidebar-title {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-secondary);
	}

	.channel-list {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-2);
	}

	.channel-item {
		width: 100%;
		display: flex;
		align-items: center;
		gap: var(--space-2);
		height: 32px;
		padding: 0 var(--space-2);
		border-radius: var(--radius-sm);
		font: var(--type-label-md);
		color: var(--text-secondary);
		text-align: left;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.channel-item :global(.icon) {
		color: var(--text-tertiary);
	}

	.channel-item:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.channel-item.active {
		background: var(--bg-active);
		color: var(--text-primary);
	}

	.channel-item.active :global(.icon) {
		color: var(--accent);
	}

	.channel-name { flex: 1; min-width: 0; }

	.channel-count {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		flex-shrink: 0;
	}

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
		gap: var(--space-4);
		min-height: var(--size-topbar);
		padding: var(--space-3) var(--space-6);
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-surface);
		flex-shrink: 0;
	}

	.header-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-heading-md);
	}

	.header-title :global(.icon) {
		color: var(--text-tertiary);
	}

	.header-topic {
		font: var(--type-body-sm);
		color: var(--text-secondary);
		margin-top: 2px;
	}

	/* The feed sits at the bottom while it is shorter than the area, as a chat does. */
	.timeline-content {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-6);
		max-width: var(--size-reader-max);
		width: 100%;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
	}

	.feed {
		margin-top: auto;
	}

	.state {
		margin: auto 0;
	}
</style>
