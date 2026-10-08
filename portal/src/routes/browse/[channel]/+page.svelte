<script lang="ts">
	// The reader: one channel's messages, oldest at the top and newest at the bottom.
	// It opens at the newest and loads older pages above (ADR 0003). A message link
	// (`?message=<id>`) opens it on that message instead, scrolled to and marked, and it
	// loads newer pages below as the reader reaches the bottom.
	//
	// Tabs in the header switch between the Messages, the channel's Media (the Media
	// screen's grid, scoped to the channel) and its Pinned messages. The tab is the URL's
	// `tab` param (none for Messages), so it survives a reload. Each tab loads the first
	// time it is shown and keeps its place while another is shown.
	import { onMount, tick, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { getMessages } from '#lib/api.ts';
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
	import MediaTimeline from '#lib/components/MediaTimeline.svelte';
	import MessageCard from '#lib/components/MessageCard.svelte';
	import MessageSkeleton from '#lib/components/MessageSkeleton.svelte';
	import TimelineFeed from '#lib/components/TimelineFeed.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';
	import Tabs from '#lib/components/ui/Tabs.svelte';

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

	// ── Tabs ──
	type ReaderTab = 'messages' | 'media' | 'pinned';
	const TABS: { value: ReaderTab; label: string; icon: 'message' | 'images' | 'pin' }[] = [
		{ value: 'messages', label: 'Messages', icon: 'message' },
		{ value: 'media', label: 'Media', icon: 'images' },
		{ value: 'pinned', label: 'Pinned', icon: 'pin' }
	];
	/** The search param that names the tab; absent for Messages. */
	const TAB_PARAM = 'tab';
	const urlTab: ReaderTab = $derived(
		TABS.find((t) => t.value === page.url.searchParams.get(TAB_PARAM))?.value ?? 'messages'
	);
	/** The tab just chosen, shown at once while the URL catches up. */
	let chosen: ReaderTab | null = $state(null);
	const tab: ReaderTab = $derived(chosen ?? urlTab);
	/** Set once the channel is found; the tabs load after that. */
	let channelReady = $state(false);
	/** The tabs shown so far: each loads the first time, and stays mounted after. */
	const visited = $state({ messages: false, media: false, pinned: false });
	/** Each tab's scroll position when another was chosen. */
	const scrollTops: Partial<Record<ReaderTab, number>> = {};
	let headerHeight = $state(0);

	$effect(() => {
		const shown = tab;
		if (!channelReady) return;
		untrack(() => {
			if (visited[shown]) return;
			visited[shown] = true;
			if (shown === 'messages') void openMessages();
			else if (shown === 'pinned') void loadPinned();
		});
	});

	/** Show tab `next`, in place of this history entry, where it was left. */
	async function setTab(next: ReaderTab) {
		const scroller = shell.scroller;
		if (scroller) scrollTops[tab] = scroller.scrollTop;
		chosen = next;
		await tick();
		const saved = scrollTops[next];
		if (scroller && saved !== undefined) scroller.scrollTop = saved;
		else if (scroller && next !== 'messages') scroller.scrollTop = 0;
		const url = new URL(page.url.href);
		if (next === 'messages') url.searchParams.delete(TAB_PARAM);
		else url.searchParams.set(TAB_PARAM, next);
		try {
			await goto(url.pathname + url.search + url.hash, { replace: true, reset: false });
		} finally {
			if (chosen === next) chosen = null;
		}
	}

	onMount(async () => {
		if (!(await findChannel())) return;
		channelReady = true;
	});

	/** Open the Messages tab: at the newest, or on the message the link names. */
	async function openMessages() {
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
	}

	// ── The Pinned tab: the channel's pinned messages, newest first ──
	let pinned: Message[] = $state([]);
	let pinnedTotal = $state(0);
	let pinnedHasMore = $state(false);
	let pinnedLoading = $state(true);
	let pinnedLoadingMore = $state(false);
	let pinnedError = $state('');

	async function loadPinned(more = false) {
		if (more && (pinnedLoadingMore || !pinnedHasMore)) return;
		pinnedLoadingMore = more;
		pinnedError = '';
		try {
			const before = more ? pinned[pinned.length - 1]?.id : undefined;
			const res = await getMessages(channelId, { pinned: true, limit, before });
			pinned = more ? [...pinned, ...res.messages] : res.messages;
			pinnedTotal = res.total;
			pinnedHasMore = res.has_more;
		} catch (e) {
			pinnedError = e instanceof Error ? e.message : 'Failed to load pinned messages';
		} finally {
			pinnedLoading = false;
			pinnedLoadingMore = false;
		}
	}

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
	<header class="reader-header" use:stickyHeader bind:offsetHeight={headerHeight}>
		<a href="/browse" class="back-link"><Icon name="arrow-left" size={14} /> Channels</a>
		{#if channel}
			<div class="title-row">
				<h1 class="title">
					<Icon name={channelIcon(channel.type)} size={18} />
					<span class="truncate">{channel.name}</span>
				</h1>
				<div class="facts">
					<Badge mono title="Messages archived">{channel.message_count.toLocaleString()} messages</Badge>
				</div>
			</div>
			{#if channel.topic}
				<p class="topic">{channel.topic}</p>
			{/if}
		{:else if !channelReady}
			<div class="title-skeleton" aria-hidden="true">
				<Skeleton width="180px" height="24px" />
			</div>
		{/if}
		<div class="reader-tabs">
			<Tabs id="reader" label="Channel views" tabs={TABS} value={tab} onchange={setTab} />
		</div>
	</header>

	<!-- The jump rail (#61) goes beside the feed, as a sticky pane in this row. -->
	<div
		class="reader-body"
		role="tabpanel"
		id="reader-panel-messages"
		aria-labelledby="reader-tab-messages"
		hidden={tab !== 'messages'}
	>
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

	{#if visited.media}
		<div
			class="tab-panel media-panel"
			role="tabpanel"
			id="reader-panel-media"
			aria-labelledby="reader-tab-media"
			hidden={tab !== 'media'}
		>
			<MediaTimeline
				{channelId}
				stickyTop={headerHeight}
				emptyTitle={channel ? `No media in #${channel.name}.` : 'No media in this channel.'}
			/>
		</div>
	{/if}

	{#if visited.pinned}
		<div
			class="tab-panel pinned-panel"
			role="tabpanel"
			id="reader-panel-pinned"
			aria-labelledby="reader-tab-pinned"
			hidden={tab !== 'pinned'}
		>
			<div class="pinned">
				{#if pinnedLoading}
					<MessageSkeleton />
				{:else if pinnedError && pinned.length === 0}
					<Alert tone="danger" title="Pinned messages could not be loaded">{pinnedError}</Alert>
				{:else if pinned.length === 0}
					<EmptyState icon="pin" title="No pinned messages in this channel." />
				{:else}
					<p class="pinned-total mono">
						{pinnedTotal.toLocaleString()} pinned message{pinnedTotal !== 1 ? 's' : ''}
					</p>
					<ol class="pinned-list">
						{#each pinned as message (message.id)}
							<li class="pinned-item">
								<MessageCard {message} />
								<a class="jump" href={channelHref(channelId, { message: message.id })}>
									<Icon name="arrow-up-right" size={14} /> Jump to message
								</a>
							</li>
						{/each}
					</ol>
					{#if pinnedError}
						<Alert tone="danger" title="Pinned messages could not be loaded">{pinnedError}</Alert>
					{/if}
					{#if pinnedHasMore}
						<LoadMore loading={pinnedLoadingMore} onclick={() => loadPinned(true)}>
							Load more pinned messages
						</LoadMore>
					{/if}
				{/if}
			</div>
		</div>
	{/if}
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

	/* The tabs sit on the header's bottom edge, their indicator over its border. */
	.reader-tabs {
		margin: var(--space-2) 0 calc(-1 * var(--space-3) - 1px);
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

	.reader-body[hidden],
	.tab-panel[hidden] {
		display: none;
	}

	.media-panel {
		padding: 0 var(--space-6) var(--space-6);
	}

	.pinned {
		width: 100%;
		max-width: var(--size-reader-max);
		margin: 0 auto;
		padding: var(--space-6);
	}

	.pinned-total {
		margin-bottom: var(--space-4);
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.pinned-list {
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.pinned-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.jump {
		align-self: flex-end;
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-label-sm);
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
		.feed-area,
		.media-panel,
		.pinned {
			padding-left: var(--space-4);
			padding-right: var(--space-4);
		}

		.title-row {
			flex-wrap: wrap;
		}
	}
</style>
