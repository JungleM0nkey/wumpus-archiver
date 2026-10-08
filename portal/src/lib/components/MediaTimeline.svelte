<!--
	A guild's media from the gallery timeline, newest (or oldest) first, in justified
	rows under sticky month headers, paging on as the end comes into view, with the one
	Lightbox over everything loaded. The Media screen shows it under its filters; Browse's
	Media tab shows it scoped to one channel.

	The filters are props: changing one replaces the grid. `total`, `loading`, `error`
	and `loaded` (the attachments loaded so far) are bindable, for a header that reports
	them.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import { getGuildGalleryTimeline } from '#lib/api.ts';
	import { mergeGroups, type MediaType } from '#lib/media.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { GalleryAttachment, TimelineGalleryGroup } from '#lib/types.ts';
	import JustifiedGrid from './JustifiedGrid.svelte';
	import Lightbox from './Lightbox.svelte';
	import LoadMore from './LoadMore.svelte';
	import Alert from './ui/Alert.svelte';
	import EmptyState from './ui/EmptyState.svelte';
	import Skeleton from './ui/Skeleton.svelte';

	let {
		channelId = null,
		authorId = null,
		type = null,
		oldestFirst = false,
		ready = true,
		stickyTop = 0,
		emptyTitle = 'No media.',
		total = $bindable(0),
		loading = $bindable(true),
		error = $bindable(''),
		loaded = $bindable([])
	}: {
		channelId?: string | null;
		authorId?: string | null;
		/** One kind of media, or null for every kind. */
		type?: MediaType | null;
		oldestFirst?: boolean;
		/** False until the screen knows what it shows; the grid waits, loading. */
		ready?: boolean;
		/** Where month headers stick, in px from the top of the scroll container. */
		stickyTop?: number;
		emptyTitle?: string;
		total?: number;
		loading?: boolean;
		error?: string;
		loaded?: GalleryAttachment[];
	} = $props();

	/** Attachments per page of the gallery timeline. */
	const PAGE_SIZE = 60;

	const filterKey = $derived(JSON.stringify([type, channelId, authorId, oldestFirst]));

	let groups: TimelineGalleryGroup[] = $state([]);
	let hasMore = $state(false);
	let offset = $state(0);
	let loadingMore = $state(false);
	/** Bumped by each reload, so a page that arrives after its filters changed is dropped. */
	let request = 0;

	const attachments = $derived(groups.flatMap((g) => g.attachments));
	$effect(() => {
		loaded = attachments;
	});

	// Load the first page whenever the filters change (and once the screen is ready).
	$effect(() => {
		void filterKey;
		if (!ready) return;
		untrack(() => void loadPage(true));
	});

	async function loadPage(reset: boolean) {
		const guild = shell.guild;
		if (!guild) {
			loading = false;
			return;
		}
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

	// ── Layout ──
	let gridWidth = $state(0);
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

	let lightbox: Lightbox | undefined = $state();

	function open(attachment: GalleryAttachment, tile: HTMLElement) {
		void lightbox?.open(attachment, tile);
	}
</script>

<div class="media-timeline" bind:clientWidth={gridWidth} style:--month-top="{stickyTop}px">
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
				<JustifiedGrid attachments={group.attachments} width={gridWidth} {targetHeight} onopen={open} />
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

<Lightbox bind:this={lightbox} {attachments} {total} onnearend={loadMore} />

<style>
	/* The gutter the screen gives the grid; month headers run across it, edge to edge. */
	.media-timeline {
		--gutter: var(--space-6);
	}

	.month + .month {
		margin-top: var(--space-2);
	}

	/* Each month's header sticks under the screen's header until the next month pushes it off. */
	.month-header {
		position: sticky;
		top: var(--month-top);
		z-index: 2;
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
		margin: 0 calc(-1 * var(--gutter));
		padding: var(--space-4) var(--gutter) var(--space-3);
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
		.media-timeline {
			--gutter: var(--space-4);
		}

		.month-header {
			padding: var(--space-3) var(--gutter) var(--space-2);
		}
	}
</style>
