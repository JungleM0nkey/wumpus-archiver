<script lang="ts">
	// The Media screen: a guild's attachments from the gallery timeline, in justified
	// rows under sticky month headers. Type, channel, author and sort are filters in the
	// URL (`type`, `channel`, `author`, `sort`), so a filtered view survives a reload
	// and can be linked to; changing one replaces the grid without leaving the screen.
	import { onMount, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { getGuild, getGuildGalleryTimeline } from '#lib/api.ts';
	import { guildHolding, shell, stickyHeader } from '#lib/shell.svelte.ts';
	import { mergeGroups, type MediaType } from '#lib/media.ts';
	import type { Channel, GalleryAttachment, TimelineGalleryGroup } from '#lib/types.ts';
	import { ChannelType } from '#lib/types.ts';
	import JustifiedGrid from '#lib/components/JustifiedGrid.svelte';
	import Lightbox from '#lib/components/Lightbox.svelte';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Chip from '#lib/components/ui/Chip.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	/** Attachments per page of the gallery timeline. */
	const PAGE_SIZE = 60;

	const TYPES: { value: MediaType | null; label: string; noun: string }[] = [
		{ value: null, label: 'All', noun: 'media' },
		{ value: 'image', label: 'Images', noun: 'images' },
		{ value: 'video', label: 'Videos', noun: 'videos' },
		{ value: 'gif', label: 'GIFs', noun: 'GIFs' }
	];

	// ── The filters, read from the URL ──
	const params = $derived(page.url.searchParams);
	const type = $derived(TYPES.find((t) => t.value && t.value === params.get('type'))?.value ?? null);
	const channelId = $derived(params.get('channel') || null);
	const authorId = $derived(params.get('author') || null);
	const oldestFirst = $derived(params.get('sort') === 'oldest');
	const filterKey = $derived(JSON.stringify([type, channelId, authorId, oldestFirst]));

	let channels: Channel[] = $state([]);
	let ready = $state(false);

	let groups: TimelineGalleryGroup[] = $state([]);
	let total = $state(0);
	let hasMore = $state(false);
	let offset = $state(0);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	/** Bumped by each reload, so a page that arrives after its filters changed is dropped. */
	let request = 0;

	const attachments = $derived(groups.flatMap((g) => g.attachments));

	const selectedChannel = $derived(channels.find((c) => c.id === channelId));
	const authorName = $derived(attachments.find((a) => a.author_name)?.author_name ?? 'one author');

	onMount(async () => {
		const guild = shell.guild;
		if (!guild) {
			loading = false;
			return;
		}
		try {
			// A link naming a channel of another guild selects that guild first.
			const detail = channelId ? await guildHolding(channelId) : null;
			if (channelId && !detail) return;
			if (!channelId) ready = true;
			const { channels: all } = detail ?? (await getGuild(guild.id));
			channels = all.filter(
				(c) =>
					c.type === ChannelType.GUILD_TEXT ||
					c.type === ChannelType.GUILD_ANNOUNCEMENT ||
					c.id === channelId
			);
			ready = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load the guild';
			loading = false;
		}
	});

	// Load the first page whenever the filters change (and once the guild is known).
	$effect(() => {
		void filterKey;
		if (!ready) return;
		untrack(() => void loadPage(true));
	});

	async function loadPage(reset: boolean) {
		const guild = shell.guild;
		if (!guild) return;
		if (reset) {
			request++;
			loading = true;
			error = '';
		} else if (loadingMore || !hasMore) {
			return;
		}
		const token = request;
		loadingMore = !reset;
		try {
			const res = await getGuildGalleryTimeline(guild.id, {
				offset: reset ? 0 : offset,
				limit: PAGE_SIZE,
				channel_id: channelId ?? undefined,
				author_id: authorId ?? undefined,
				content_type: type ?? 'media',
				order: oldestFirst ? 'oldest' : undefined
			});
			if (token !== request) return;
			groups = mergeGroups(reset ? [] : groups, res.groups);
			offset = (reset ? 0 : offset) + res.groups.reduce((n, g) => n + g.attachments.length, 0);
			total = res.total;
			hasMore = res.has_more;
		} catch (e) {
			if (token !== request) return;
			error = e instanceof Error ? e.message : 'Failed to load media';
		} finally {
			if (token === request) {
				loading = false;
				loadingMore = false;
			}
		}
	}

	function loadMore() {
		void loadPage(false);
	}

	/** Change one filter in the URL; the grid follows. */
	function setFilter(name: string, value: string | null) {
		// Build on a navigation still under way, so two quick changes both land.
		const from = pending ?? page.url.href;
		const url = new URL(from);
		if (value) url.searchParams.set(name, value);
		else url.searchParams.delete(name);
		if (url.href === from) return;
		const scroller = shell.scroller;
		if (scroller && scroller.scrollTop > 0) scroller.scrollTop = 0;
		const href = (pending = url.href);
		void goto(url.pathname + url.search, { reset: false }).finally(() => {
			if (pending === href) pending = null;
		});
	}

	/** The URL a filter change is navigating to, until it arrives. */
	let pending: string | null = null;

	// ── Layout ──
	let gridWidth = $state(0);
	let headerHeight = $state(0);
	const targetHeight = $derived(gridWidth < 560 ? 120 : 180);

	// ── Paging as the end of the grid comes into view ──
	let sentinel: HTMLElement | undefined = $state();
	$effect(() => {
		if (!sentinel) return;
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((e) => e.isIntersecting)) loadMore();
			},
			{ root: shell.scroller, rootMargin: '0px 0px 600px 0px' }
		);
		observer.observe(sentinel);
		return () => observer.disconnect();
	});

	// ── The lightbox: one, over every loaded attachment ──
	let lightboxIndex: number | null = $state(null);
	const lightboxAttachment = $derived(lightboxIndex === null ? null : (attachments[lightboxIndex] ?? null));

	function open(attachment: GalleryAttachment) {
		lightboxIndex = attachments.findIndex((a) => a.id === attachment.id);
	}

	function step(by: number) {
		if (lightboxIndex === null) return;
		const next = lightboxIndex + by;
		if (next < 0 || next >= attachments.length) return;
		lightboxIndex = next;
		if (next >= attachments.length - 3) loadMore();
	}

	const noun = $derived(TYPES.find((t) => t.value === type)?.noun ?? 'media');
	const emptyTitle = $derived(
		`No ${noun}${selectedChannel ? ` in #${selectedChannel.name}` : ''}${authorId ? ' from this author' : ''}.`
	);
</script>

<div class="media-page" style:--media-header-height="{headerHeight}px">
	<header class="media-header" use:stickyHeader bind:offsetHeight={headerHeight}>
		<div class="title-row">
			<h1>Media</h1>
			{#if !loading && !error}
				<span class="total mono">{total.toLocaleString()} item{total !== 1 ? 's' : ''}</span>
			{/if}
		</div>
		<div class="toolbar">
			<div class="chips" role="group" aria-label="Type">
				{#each TYPES as t (t.label)}
					<Chip selected={type === t.value} onclick={() => setFilter('type', t.value)}>{t.label}</Chip>
				{/each}
			</div>
			<label class="field">
				<span class="field-label">Channel</span>
				<select
					class="select"
					value={channelId ?? ''}
					onchange={(e) => setFilter('channel', e.currentTarget.value || null)}
				>
					<option value="">All channels</option>
					{#each channels as ch (ch.id)}
						<option value={ch.id}>#{ch.name}</option>
					{/each}
				</select>
			</label>
			<label class="field">
				<span class="field-label">Sort</span>
				<select
					class="select"
					value={oldestFirst ? 'oldest' : 'newest'}
					onchange={(e) => setFilter('sort', e.currentTarget.value === 'oldest' ? 'oldest' : null)}
				>
					<option value="newest">Newest first</option>
					<option value="oldest">Oldest first</option>
				</select>
			</label>
			{#if authorId}
				<Chip selected icon="x" aria-label="Clear author filter" onclick={() => setFilter('author', null)}>
					From {authorName}
				</Chip>
			{/if}
		</div>
	</header>

	<div class="media-body">
		<div bind:clientWidth={gridWidth}>
			{#if loading}
				<div class="skeletons" aria-busy="true">
					<span class="sr-only" role="status">Loading media…</span>
					<Skeleton width="120px" height="20px" />
					{#each [0, 1] as r (r)}
						<div class="skeleton-row">
							{#each [26, 18, 30, 22] as w (w)}
								<Skeleton width="{w}%" height="{targetHeight}px" radius="xs" />
							{/each}
						</div>
					{/each}
				</div>
			{:else if error}
				<Alert tone="danger" title="Media could not be loaded">{error}</Alert>
			{:else if groups.length === 0}
				<EmptyState icon="image-off" title={emptyTitle} />
			{:else}
				{#each groups as group, gi (group.period)}
					{@const more = hasMore && gi === groups.length - 1}
					<section class="month" aria-labelledby="month-{group.period}">
						<h2 class="month-header" id="month-{group.period}">
							<span class="month-label">{group.label}</span>
							<span class="month-count mono">
								{group.count}{more ? '+' : ''} item{group.count !== 1 || more ? 's' : ''}
							</span>
						</h2>
						<JustifiedGrid
							attachments={group.attachments}
							width={gridWidth}
							{targetHeight}
							onopen={open}
						/>
					</section>
				{/each}
				{#if hasMore}
					{#key offset}
						<div class="sentinel" bind:this={sentinel} aria-hidden="true"></div>
					{/key}
					<LoadMore loading={loadingMore} onclick={loadMore}>Load more</LoadMore>
				{/if}
			{/if}
		</div>
	</div>
</div>

{#if lightboxAttachment && lightboxIndex !== null}
	<Lightbox
		attachment={lightboxAttachment}
		hasPrev={lightboxIndex > 0}
		hasNext={lightboxIndex < attachments.length - 1}
		onclose={() => (lightboxIndex = null)}
		onprev={() => step(-1)}
		onnext={() => step(1)}
	/>
{/if}

<style>
	.media-page {
		min-height: 100%;
	}

	.media-header {
		position: sticky;
		top: 0;
		z-index: 3;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4) var(--space-6);
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
	}

	.title-row {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
	}

	.title-row h1 {
		font: var(--type-heading-lg);
	}

	.total {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.toolbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-4);
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
	}

	.field {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
	}

	.field-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.select {
		height: 28px;
		max-width: 220px;
		padding: 0 var(--space-2);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		background: var(--bg-raised);
		color: var(--text-primary);
		font: var(--type-label-sm);
		cursor: pointer;
	}

	.select option {
		background: var(--bg-raised);
		color: var(--text-primary);
	}

	.media-body {
		padding: 0 var(--space-6) var(--space-6);
	}

	.month + .month {
		margin-top: var(--space-2);
	}

	/* Each month's header sticks under the screen's header until the next month pushes it off. */
	.month-header {
		position: sticky;
		top: var(--media-header-height);
		z-index: 2;
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
		margin: 0 calc(-1 * var(--space-6));
		padding: var(--space-4) var(--space-6) var(--space-3);
		background: color-mix(in srgb, var(--bg-canvas) 92%, transparent);
		backdrop-filter: blur(8px);
	}

	.month-label {
		font: var(--type-heading-md);
		color: var(--text-primary);
	}

	.month-count {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.skeletons {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding-top: var(--space-4);
	}

	.skeleton-row {
		display: flex;
		gap: 4px;
	}

	.sentinel {
		height: 1px;
	}

	@media (max-width: 767px) {
		.media-header {
			padding: var(--space-3) var(--space-4);
		}
		.media-body {
			padding: 0 var(--space-4) var(--space-4);
		}
		.month-header {
			margin: 0 calc(-1 * var(--space-4));
			padding: var(--space-3) var(--space-4) var(--space-2);
		}
	}
</style>
