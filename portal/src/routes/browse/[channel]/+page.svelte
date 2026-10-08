<script lang="ts">
	// The reader: one channel's messages, oldest at the top and newest at the bottom.
	// It opens at the newest and loads older pages above (ADR 0003). A message link
	// (`?message=<id>`) opens it on that message instead, scrolled to and marked, and it
	// loads newer pages below as the reader reaches the bottom.
	import { onMount, tick } from 'svelte';
	import { page } from '$app/state';
	import { getBrowseGuild } from '#lib/browse.ts';
	import { channelIcon } from '#lib/channels.ts';
	import {
		keepingPosition,
		newerPage,
		newestPage,
		olderPage,
		pageAround,
		scrollToBottom
	} from '#lib/reader.ts';
	import { channelHref } from '#lib/routes.ts';
	import { guildHolding, shell, stickyHeader } from '#lib/shell.svelte.ts';
	import type { Channel, Message } from '#lib/types.ts';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import MessageSkeleton from '#lib/components/MessageSkeleton.svelte';
	import TimelineFeed from '#lib/components/TimelineFeed.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	// The layout remounts this page for another channel or message link.
	const channelId = page.params.channel ?? '';
	const messageId = page.url.searchParams.get('message');

	const browse = getBrowseGuild();
	const limit = 50;

	let channel: Channel | null = $state(null);
	let messages: Message[] = $state([]);
	let hasOlder = $state(false);
	let hasNewer = $state(false);
	let loading = $state(true);
	let loadingOlder = $state(false);
	let loadingNewer = $state(false);
	let error = $state('');
	/** The message the link opened the reader on, once it is loaded. */
	let anchor: string | null = $state(null);
	/** Set once the reader has scrolled to where it opens; newer pages load after that. */
	let settled = $state(false);
	let newerEdge: HTMLElement | undefined = $state();

	onMount(async () => {
		if (!(await findChannel())) return;
		try {
			if (messageId) {
				const around = await pageAround(channelId, messageId, limit);
				({ messages, hasOlder, hasNewer } = around);
				anchor = messages.some((m) => m.id === messageId) ? messageId : null;
			} else {
				const newest = await newestPage(channelId, limit);
				messages = newest.messages;
				hasOlder = newest.hasMore;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load messages';
		} finally {
			loading = false;
		}
		if (anchor) await scrollToMessage(anchor);
		else await scrollToBottom(shell.scroller);
		settled = true;
	});

	/** Find the channel in the guild; false when the shell moves to the guild that holds it. */
	async function findChannel(): Promise<boolean> {
		if (!(await browse.ready)) return false;
		channel = browse.detail?.channels.find((c) => c.id === channelId) ?? null;
		if (channel || browse.checked === channelId) return true;
		// A link from inside Browse to a channel of another guild.
		try {
			const detail = await guildHolding(channelId);
			if (!detail && shell.guild) return false;
			channel = detail?.channels.find((c) => c.id === channelId) ?? null;
		} catch (e) {
			console.error('Failed to find the channel:', e);
		}
		return true;
	}

	async function scrollToMessage(id: string) {
		await tick();
		const card = shell.scroller?.querySelector(`[data-message-id="${CSS.escape(id)}"]`);
		card?.scrollIntoView({ block: 'center' });
	}

	async function loadOlder() {
		if (loadingOlder || !hasOlder || messages.length === 0) return;
		loadingOlder = true;
		try {
			const older = await olderPage(channelId, messages[0], limit);
			await keepingPosition(shell.scroller, () => {
				messages = [...older.messages, ...messages];
				hasOlder = older.hasMore;
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load older messages';
		} finally {
			loadingOlder = false;
		}
	}

	async function loadNewer() {
		if (loadingNewer || !hasNewer || messages.length === 0) return;
		loadingNewer = true;
		try {
			const newer = await newerPage(channelId, messages[messages.length - 1], limit);
			messages = [...messages, ...newer.messages];
			hasNewer = newer.hasMore;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load newer messages';
		} finally {
			loadingNewer = false;
		}
	}

	// Reaching the bottom of a feed that stops short of the newest loads the next page.
	// The observer is made again after each page, so it fires again while the edge is
	// still in view.
	$effect(() => {
		const edge = newerEdge;
		const root = shell.scroller;
		if (!edge || !root || !settled || loadingNewer) return;
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((entry) => entry.isIntersecting)) void loadNewer();
			},
			{ root, rootMargin: '0px 0px 200px 0px' }
		);
		observer.observe(edge);
		return () => observer.disconnect();
	});
</script>

<div class="reader">
	<header class="reader-header" use:stickyHeader>
		<a href="/browse" class="back-link"><Icon name="arrow-left" size={14} /> Channels</a>
		{#if channel}
			<div class="title-row">
				<h1 class="title">
					<Icon name={channelIcon(channel.type)} size={18} />
					<span class="truncate">{channel.name}</span>
				</h1>
				<div class="facts">
					<Badge mono title="Messages archived">{channel.message_count.toLocaleString()} messages</Badge>
					<a href="/media?channel={channelId}" class="media-link">
						<Icon name="images" size={14} /> Media
					</a>
				</div>
			</div>
			{#if channel.topic}
				<p class="topic">{channel.topic}</p>
			{/if}
		{:else if loading}
			<div class="title-skeleton" aria-hidden="true">
				<Skeleton width="180px" height="24px" />
			</div>
		{/if}
	</header>

	<!-- The jump rail (#61) goes beside the feed, as a sticky pane in this row. -->
	<div class="reader-body">
		<div class="feed-area">
			{#if loading}
				<div class="feed"><MessageSkeleton /></div>
			{:else if error && messages.length === 0}
				<div class="state">
					<Alert tone="danger" title="Messages could not be loaded">{error}</Alert>
				</div>
			{:else if messages.length === 0}
				<div class="state">
					<EmptyState icon="inbox" title="No messages archived in this channel." />
				</div>
			{:else}
				<div class="feed">
					{#if hasOlder}
						<LoadMore loading={loadingOlder} onclick={loadOlder}>Load older messages</LoadMore>
					{:else}
						<div class="end-marker mono">Beginning of the channel</div>
					{/if}

					<TimelineFeed {messages} highlight={anchor} />

					{#if error}
						<div class="state"><Alert tone="danger" title="Messages could not be loaded">{error}</Alert></div>
					{/if}

					{#if hasNewer}
						<div bind:this={newerEdge}>
							<LoadMore loading={loadingNewer} onclick={loadNewer}>Load newer messages</LoadMore>
						</div>
						<a class="newest-pill" href={channelHref(channelId)}>
							<Icon name="arrow-down" size={14} /> Newest messages
						</a>
					{/if}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	/* At least the shell's height, so the feed can sit at its bottom. */
	.reader {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.reader-header {
		position: sticky;
		top: 0;
		z-index: 2;
		display: flex;
		flex-direction: column;
		justify-content: center;
		min-height: var(--size-topbar);
		padding: var(--space-3) var(--space-6);
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-surface);
		flex-shrink: 0;
	}

	/* Only below 768px, where the reader replaces the channel pane. */
	.back-link {
		display: none;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-label-sm);
		color: var(--text-tertiary);
		margin-bottom: var(--space-2);
	}

	.back-link:hover {
		color: var(--text-primary);
	}

	.title-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-4);
	}

	.title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
		font: var(--type-heading-md);
		color: var(--text-primary);
	}

	.title :global(.icon) {
		color: var(--text-tertiary);
	}

	.facts {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		flex-shrink: 0;
	}

	.media-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-label-sm);
	}

	.topic {
		font: var(--type-body-sm);
		color: var(--text-secondary);
		margin-top: 2px;
	}

	.title-skeleton {
		padding: var(--space-1) 0;
	}

	.reader-body {
		flex: 1;
		display: flex;
	}

	/* The feed sits at the bottom while it is shorter than the area, as a chat does. */
	.feed-area {
		flex: 1;
		min-width: 0;
		padding: var(--space-6);
		display: flex;
		flex-direction: column;
	}

	.feed {
		width: 100%;
		max-width: var(--size-reader-max);
		margin: auto auto 0;
	}

	.state {
		width: 100%;
		max-width: var(--size-reader-max);
		margin: auto;
		padding: var(--space-4) 0;
	}

	.end-marker {
		text-align: center;
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		padding: var(--space-8) 0;
	}

	/* Back to the newest messages from a feed opened on an older one. */
	.newest-pill {
		position: sticky;
		bottom: var(--space-4);
		display: flex;
		align-items: center;
		gap: var(--space-1);
		width: fit-content;
		margin: 0 auto;
		padding: var(--space-2) var(--space-4);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-full);
		background: var(--bg-overlay);
		box-shadow: var(--shadow-floating);
		font: var(--type-label-sm);
		color: var(--text-primary);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.newest-pill:hover {
		border-color: var(--border-strong);
		color: var(--text-primary);
	}

	@media (max-width: 767px) {
		.back-link {
			display: inline-flex;
		}

		.reader-header,
		.feed-area {
			padding-left: var(--space-4);
			padding-right: var(--space-4);
		}

		.title-row {
			flex-wrap: wrap;
		}
	}
</style>
