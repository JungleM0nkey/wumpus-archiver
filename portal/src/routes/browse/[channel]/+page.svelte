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
	//
	// Beside the feed, the jump rail (#61) lists the channel's months; picking one reads
	// the page around that month's first message and puts it at the top of the view. A
	// reply's link scrolls to the message it answers when it is loaded. On the Messages
	// tab, J and K move the keyboard focus from message to message, and G then L goes to
	// the newest; these keys are the reader's own and do nothing while typing in a field.
	import { onMount, tick, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { getChannelActivity, getMessages } from '#lib/api.ts';
	import { getBrowseGuild } from '#lib/browse.ts';
	import { channelIcon } from '#lib/channels.ts';
	import { messageMonth } from '#lib/feed.ts';
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
	import type { Channel, ChannelActivityBucket, Message, MessageReference } from '#lib/types.ts';
	import JumpRail from '#lib/components/JumpRail.svelte';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import MediaTimeline from '#lib/components/MediaTimeline.svelte';
	import MessageCard from '#lib/components/MessageCard.svelte';
	import MessageFeed from '#lib/components/MessageFeed.svelte';
	import MessageSkeleton from '#lib/components/MessageSkeleton.svelte';
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
	/** How long after G an L still completes "G then L". */
	const CHORD_MS = 1500;

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
	let feedEl: HTMLElement | undefined = $state();

	/** The channel's months for the jump rail; null while they load. */
	let months: ChannelActivityBucket[] | null = $state(null);
	/** The month of the message at the top of the view, YYYY-MM. */
	let currentMonth: string | null = $state(null);
	/** The message a month was picked at, kept at the top of the view. */
	let jumpTarget: string | null = $state(null);
	/** Room below the feed, so a month's first message can reach the top of the view. */
	let spacer = $state(0);
	let jumping = false;

	/** The message a reply's link was just followed to. */
	let flashId: string | null = $state(null);
	/** The row Tab reaches in the feed (roving focus); J and K move it. */
	let focusId: string | null = $state(null);
	const focusable = $derived(
		focusId && messages.some((m) => m.id === focusId)
			? focusId
			: (anchor ?? messages[messages.length - 1]?.id ?? null)
	);

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
		void loadMonths();
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
		trackMonth();
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

	/** Read the channel's months for the jump rail; without them the rail is left out. */
	async function loadMonths() {
		try {
			months = (await getChannelActivity(channelId)).buckets;
		} catch {
			months = [];
		}
	}

	/** The row of message `id` in the feed, when it is loaded. */
	function rowOf(id: string): HTMLElement | null {
		return feedEl?.querySelector<HTMLElement>(`[data-message-id="${CSS.escape(id)}"]`) ?? null;
	}

	async function scrollToMessage(id: string) {
		await tick();
		rowOf(id)?.scrollIntoView({ block: 'center' });
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
			await tick();
			fitSpacer();
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

	// ── The jump rail ───────────────────────────────────────────────────────────

	/** Where `el` starts in the scroller's content, in px from its top. */
	function offsetIn(scroller: HTMLElement, el: HTMLElement): number {
		return el.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
	}

	/** What goes at the top of the view for message `id`: its day's pill when it opens the day. */
	function topOf(id: string): HTMLElement | null {
		const row = rowOf(id);
		const day = row?.closest<HTMLElement>('[data-day]');
		return day && day.querySelector('[data-message-id]') === row ? day : row;
	}

	/** Size the room below the feed so the picked month's first message can reach the top. */
	function fitSpacer() {
		const scroller = shell.scroller;
		const target = jumpTarget ? topOf(jumpTarget) : null;
		if (!scroller || !target) {
			spacer = 0;
			return;
		}
		const below = scroller.scrollHeight - spacer - offsetIn(scroller, target);
		spacer = Math.max(0, Math.ceil(scroller.clientHeight - headerHeight - below));
	}

	async function jumpTo(bucket: ChannelActivityBucket) {
		if (jumping) return;
		jumping = true;
		try {
			const around = await pageAround(channelId, bucket.first_message_id, limit);
			messages = around.messages;
			hasOlder = around.hasOlder;
			hasNewer = around.hasNewer;
			anchor = null;
			error = '';
			jumpTarget = bucket.first_message_id;
			focusId = bucket.first_message_id;
			await tick();
			fitSpacer();
			await tick();
			const scroller = shell.scroller;
			const target = topOf(bucket.first_message_id);
			if (scroller && target) scroller.scrollTop = offsetIn(scroller, target) - headerHeight;
			currentMonth = bucket.start.slice(0, 7);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load the month';
		} finally {
			jumping = false;
		}
	}

	/** Mark the month of the message at the top of the view in the rail. */
	function trackMonth() {
		const scroller = shell.scroller;
		if (!scroller || !feedEl) return;
		const top = scroller.getBoundingClientRect().top + headerHeight;
		for (const row of feedEl.querySelectorAll<HTMLElement>('[data-message-id]')) {
			if (row.getBoundingClientRect().bottom <= top) continue;
			const message = messages.find((m) => m.id === row.dataset.messageId);
			if (message) currentMonth = messageMonth(message);
			return;
		}
	}

	$effect(() => {
		const scroller = shell.scroller;
		if (!scroller || !settled) return;
		let frame = 0;
		const onScroll = () => {
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(trackMonth);
		};
		scroller.addEventListener('scroll', onScroll, { passive: true });
		return () => {
			cancelAnimationFrame(frame);
			scroller.removeEventListener('scroll', onScroll);
		};
	});

	// ── Replies ─────────────────────────────────────────────────────────────────

	/** Follow a reply to the message it answers: in place when it is loaded here. */
	async function followReference(reference: MessageReference, event: MouseEvent) {
		if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
			return;
		}
		const row = reference.channel_id === channelId ? rowOf(reference.id) : null;
		if (!row) return; // The link opens the message in context.
		event.preventDefault();
		row.scrollIntoView({ block: 'center' });
		focusId = reference.id;
		row.focus({ preventScroll: true });
		flashId = null;
		await tick();
		flashId = reference.id;
	}

	// ── The newest messages ─────────────────────────────────────────────────────

	/** Show the channel's newest messages at the bottom of the view. */
	async function toNewest() {
		if (messageId) {
			// Leave the message link, as the Newest messages pill does.
			await goto(channelHref(channelId));
			return;
		}
		if (hasNewer) {
			try {
				const newest = await newestPage(channelId, limit);
				messages = newest.messages;
				hasOlder = newest.hasMore;
				hasNewer = false;
				anchor = null;
			} catch (e) {
				error = e instanceof Error ? e.message : 'Failed to load messages';
				return;
			}
		}
		jumpTarget = null;
		spacer = 0;
		await scrollToBottom(shell.scroller);
	}

	function onNewestPill(event: MouseEvent) {
		if (messageId || event.metaKey || event.ctrlKey || event.shiftKey) return;
		event.preventDefault();
		void toNewest();
	}

	// ── Keys ────────────────────────────────────────────────────────────────────

	let chord: ReturnType<typeof setTimeout> | undefined;

	function isTyping(target: EventTarget | null): boolean {
		if (!(target instanceof HTMLElement)) return false;
		return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
		if (isTyping(event.target) || loading || tab !== 'messages') return;
		const key = event.key.toLowerCase();
		if (chord !== undefined) {
			clearTimeout(chord);
			chord = undefined;
			if (key === 'l') {
				event.preventDefault();
				void toNewest().then(focusNewest);
				return;
			}
		}
		if (event.shiftKey) return;
		if (key === 'g') {
			chord = setTimeout(() => (chord = undefined), CHORD_MS);
		} else if (key === 'j' || key === 'k') {
			event.preventDefault();
			void move(key === 'j' ? 1 : -1);
		}
	}

	function rows(): HTMLElement[] {
		return [...(feedEl?.querySelectorAll<HTMLElement>('[data-message-id]') ?? [])];
	}

	/** The first row whose top is in view below the header, else the first one partly in view. */
	function firstInView(list: HTMLElement[]): number {
		const scroller = shell.scroller;
		if (!scroller) return 0;
		const bounds = scroller.getBoundingClientRect();
		const top = bounds.top + headerHeight;
		const whole = list.findIndex((row) => row.getBoundingClientRect().top >= top - 1);
		if (whole !== -1 && list[whole].getBoundingClientRect().top < bounds.bottom) return whole;
		const partly = list.findIndex((row) => row.getBoundingClientRect().bottom > top);
		return partly === -1 ? list.length - 1 : partly;
	}

	/** Move the keyboard focus `step` messages down (newer) or up (older). */
	async function move(step: 1 | -1) {
		let list = rows();
		if (list.length === 0) return;
		const focused = document.activeElement?.closest<HTMLElement>('[data-message-id]') ?? null;
		let index = focused ? list.indexOf(focused) : -1;
		let next: number;
		if (index === -1) {
			next = firstInView(list);
		} else {
			next = index + step;
			if (next < 0 && hasOlder) {
				await loadOlder();
				list = rows();
				index = list.indexOf(focused!);
				next = index + step;
			} else if (next >= list.length && hasNewer) {
				await loadNewer();
				list = rows();
				next = list.indexOf(focused!) + step;
			}
			next = Math.max(0, Math.min(list.length - 1, next));
		}
		focusRow(list[next]);
	}

	function focusRow(row: HTMLElement | undefined) {
		if (!row) return;
		focusId = row.dataset.messageId ?? null;
		row.focus({ preventScroll: true });
		row.scrollIntoView({ block: 'nearest' });
	}

	function focusNewest() {
		const list = rows();
		const row = list[list.length - 1];
		if (!row) return;
		focusId = row.dataset.messageId ?? null;
		row.focus({ preventScroll: true });
	}

	/** Clicking or tabbing into a row makes it the one Tab reaches. */
	function onfocusin(event: FocusEvent) {
		const row = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-message-id]');
		if (row?.dataset.messageId) focusId = row.dataset.messageId;
	}
</script>

<svelte:window {onkeydown} />

<div class="reader" style:--reader-header-height="{headerHeight}px">
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

	<!-- The feed, and the jump rail beside it as a sticky pane in this row. -->
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
				<div class="feed" bind:this={feedEl} {onfocusin}>
					{#if hasOlder}
						<LoadMore loading={loadingOlder} onclick={loadOlder}>Load older messages</LoadMore>
					{:else}
						<div class="end-marker mono">Beginning of the channel</div>
					{/if}

					<MessageFeed
						{messages}
						highlight={anchor}
						flash={flashId}
						{focusable}
						busy={loadingOlder || loadingNewer}
						onreference={followReference}
					/>

					{#if error}
						<div class="state"><Alert tone="danger" title="Messages could not be loaded">{error}</Alert></div>
					{/if}

					{#if hasNewer}
						<div bind:this={newerEdge}>
							<LoadMore loading={loadingNewer} onclick={loadNewer}>Load newer messages</LoadMore>
						</div>
						<a class="newest-pill" href={channelHref(channelId)} onclick={onNewestPill}>
							<Icon name="arrow-down" size={14} /> Newest messages
						</a>
					{/if}
				</div>
				{#if spacer > 0}
					<div class="spacer" style:height="{spacer}px" aria-hidden="true"></div>
				{/if}
			{/if}
		</div>

		{#if months === null || months.length > 0}
			<aside class="rail-pane">
				<JumpRail buckets={months} current={currentMonth} onjump={jumpTo} />
			</aside>
		{/if}
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

	/* The rail is sticky beside the feed, so the row does not stretch it. */
	.reader-body {
		flex: 1;
		display: flex;
		align-items: flex-start;
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
		align-self: stretch;
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

	.spacer {
		flex-shrink: 0;
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
		z-index: 1;
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

	/* The jump rail stays in view below the header and scrolls its own list. */
	.rail-pane {
		position: sticky;
		top: var(--reader-header-height);
		width: 192px;
		flex-shrink: 0;
		height: calc(var(--shell-viewport-height) - var(--reader-header-height));
		overflow-y: auto;
		overscroll-behavior: contain;
		border-left: 1px solid var(--border-subtle);
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

		.rail-pane {
			display: none;
		}
	}
</style>
