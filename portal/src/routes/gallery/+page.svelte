<script lang="ts">
	import { onMount } from 'svelte';
	import { getGuilds, getGuild, getGuildGallery, getGuildGalleryTimeline } from '#lib/api.ts';
	import type { GalleryAttachment, Channel, GuildDetail, TimelineGalleryGroup } from '#lib/types.ts';
	import { ChannelType } from '#lib/types.ts';
	import GalleryGrid from '#lib/components/GalleryGrid.svelte';
	import Lightbox from '#lib/components/Lightbox.svelte';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import Chip from '#lib/components/ui/Chip.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	type ViewMode = 'grid' | 'timeline';
	type GroupBy = 'week' | 'month' | 'year';

	let guild: GuildDetail | null = $state(null);
	let channels: Channel[] = $state([]);
	let loading = $state(true);
	let error = $state('');

	// View state
	let viewMode: ViewMode = $state('grid');
	let groupBy: GroupBy = $state('month');
	let selectedChannel: string | null = $state(null);

	// Grid view state
	let gridAttachments: GalleryAttachment[] = $state([]);
	let gridTotal = $state(0);
	let gridHasMore = $state(false);
	let gridOffset = $state(0);
	let gridLoading = $state(false);

	// Timeline view state
	let timelineGroups: TimelineGalleryGroup[] = $state([]);
	let timelineTotal = $state(0);
	let timelineHasMore = $state(false);
	let timelineOffset = $state(0);
	let timelineLoading = $state(false);

	// Lightbox state (for timeline view)
	let lightboxOpen = $state(false);
	let lightboxAttachments: GalleryAttachment[] = $state([]);
	let lightboxIndex = $state(0);

	let lightboxAttachment = $derived(lightboxAttachments[lightboxIndex] ?? null);
	let lightboxHasPrev = $derived(lightboxIndex > 0);
	let lightboxHasNext = $derived(lightboxIndex < lightboxAttachments.length - 1);

	const limit = 60;
	const timelineGroupLimit = 6;

	onMount(async () => {
		try {
			const guilds = await getGuilds();
			if (guilds.length > 0) {
				guild = await getGuild(guilds[0].id);
				channels = guild.channels.filter(
					(ch) => ch.type === ChannelType.GUILD_TEXT || ch.type === ChannelType.GUILD_ANNOUNCEMENT
				);
				await loadContent();
			} else {
				loading = false;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load';
			loading = false;
		}
	});

	async function loadContent() {
		loading = true;
		error = '';
		if (viewMode === 'grid') {
			await loadGrid(true);
		} else {
			await loadTimeline(true);
		}
		loading = false;
	}

	async function loadGrid(reset = false) {
		if (!guild) return;
		if (reset) {
			gridAttachments = [];
			gridOffset = 0;
		}
		gridLoading = true;
		try {
			const res = await getGuildGallery(guild.id, {
				limit,
				offset: reset ? 0 : gridOffset,
				channel_id: selectedChannel ?? undefined
			});
			if (reset) {
				gridAttachments = res.attachments;
			} else {
				gridAttachments = [...gridAttachments, ...res.attachments];
			}
			gridTotal = res.total;
			gridHasMore = res.has_more;
			gridOffset = reset ? res.attachments.length : gridOffset + res.attachments.length;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load gallery';
		} finally {
			gridLoading = false;
		}
	}

	async function loadTimeline(reset = false) {
		if (!guild) return;
		if (reset) {
			timelineGroups = [];
			timelineOffset = 0;
		}
		timelineLoading = true;
		try {
			const res = await getGuildGalleryTimeline(guild.id, {
				limit: timelineGroupLimit,
				offset: reset ? 0 : timelineOffset,
				channel_id: selectedChannel ?? undefined,
				group_by: groupBy
			});
			if (reset) {
				timelineGroups = res.groups;
			} else {
				timelineGroups = [...timelineGroups, ...res.groups];
			}
			timelineTotal = res.total;
			timelineHasMore = res.has_more;
			timelineOffset = reset ? res.groups.length : timelineOffset + res.groups.length;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load timeline';
		} finally {
			timelineLoading = false;
		}
	}

	async function loadMoreGrid() {
		if (gridLoading || !gridHasMore) return;
		await loadGrid(false);
	}

	async function loadMoreTimeline() {
		if (timelineLoading || !timelineHasMore) return;
		await loadTimeline(false);
	}

	async function switchView(mode: ViewMode) {
		if (viewMode === mode) return;
		viewMode = mode;
		await loadContent();
	}

	async function switchGroupBy(g: GroupBy) {
		if (groupBy === g) return;
		groupBy = g;
		if (viewMode === 'timeline') {
			await loadContent();
		}
	}

	async function filterChannel(id: string | null) {
		if (selectedChannel === id) return;
		selectedChannel = id;
		await loadContent();
	}

	function openLightbox(groupIdx: number, imgIdx: number) {
		const group = timelineGroups[groupIdx];
		if (!group) return;
		lightboxAttachments = group.attachments;
		lightboxIndex = imgIdx;
		lightboxOpen = true;
	}


	let totalCount = $derived(viewMode === 'grid' ? gridTotal : timelineTotal);
</script>

<div class="gallery-page">
	<aside class="sidebar">
		<!-- View mode -->
		<div class="sidebar-section">
			<h2 class="sidebar-label">View</h2>
			<div class="chip-row">
				<Chip icon="grid" selected={viewMode === 'grid'} onclick={() => switchView('grid')}>Grid</Chip>
				<Chip icon="rows" selected={viewMode === 'timeline'} onclick={() => switchView('timeline')}>
					Timeline
				</Chip>
			</div>
		</div>

		<!-- Group by (timeline only) -->
		{#if viewMode === 'timeline'}
			<div class="sidebar-section">
				<h2 class="sidebar-label">Group by</h2>
				<div class="chip-row">
					{#each (['week', 'month', 'year'] as const) as g (g)}
						<Chip selected={groupBy === g} onclick={() => switchGroupBy(g)}>
							<span class="capitalize">{g}</span>
						</Chip>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Channel filter -->
		<div class="sidebar-section sidebar-section--grow">
			<h2 class="sidebar-label">Channels</h2>
			<div class="channel-list">
				<button
					class="channel-item"
					class:active={selectedChannel === null}
					aria-pressed={selectedChannel === null}
					onclick={() => filterChannel(null)}
				>
					<Icon name="layers" />
					<span class="channel-name">All channels</span>
				</button>
				{#each channels as ch (ch.id)}
					<button
						class="channel-item"
						class:active={selectedChannel === ch.id}
						aria-pressed={selectedChannel === ch.id}
						onclick={() => filterChannel(ch.id)}
					>
						<Icon name="hash" />
						<span class="channel-name">{ch.name}</span>
					</button>
				{/each}
			</div>
		</div>
	</aside>

	<div class="gallery-main">
		<header class="gallery-header">
			<div class="header-row">
				<h1>Gallery</h1>
				{#if selectedChannel}
					{@const ch = channels.find(c => c.id === selectedChannel)}
					{#if ch}
						<Badge tone="accent" icon="hash">{ch.name}</Badge>
					{/if}
				{/if}
			</div>
			{#if totalCount > 0}
				<div class="header-meta mono">
					{totalCount.toLocaleString()} item{totalCount !== 1 ? 's' : ''}
					{#if viewMode === 'timeline'}
						&middot; grouped by {groupBy}
					{/if}
				</div>
			{/if}
		</header>

		<div class="gallery-body">
			{#if loading}
				<div class="thumb-skeletons" aria-busy="true">
					<span class="sr-only" role="status">Loading gallery…</span>
					{#each Array.from({ length: 12 }, (_, i) => i) as i (i)}
						<Skeleton aspect="1" radius="sm" />
					{/each}
				</div>
			{:else if error}
				<Alert tone="danger" title="The gallery could not be loaded">{error}</Alert>
			{:else if viewMode === 'grid'}
				<!-- Grid view -->
				{#if gridAttachments.length === 0}
					<EmptyState icon="image-off" title="No images found{selectedChannel ? ' in this channel' : ''}." />
				{:else}
					<GalleryGrid
						attachments={gridAttachments}
						loading={gridLoading}
						hasMore={gridHasMore}
						onloadmore={loadMoreGrid}
					/>
				{/if}
			{:else}
				<!-- Timeline view -->
				{#if timelineGroups.length === 0}
					<EmptyState icon="image-off" title="No images found{selectedChannel ? ' in this channel' : ''}." />
				{:else}
					<div class="timeline">
						{#each timelineGroups as group, gi (group.period)}
							<section class="timeline-group">
								<div class="timeline-header">
									<h2 class="timeline-label">{group.label}</h2>
									<span class="timeline-count mono">{group.count} image{group.count !== 1 ? 's' : ''}</span>
								</div>
								<div class="timeline-grid">
									{#each group.attachments as att, ai (att.id)}
										<button
											class="timeline-thumb"
											aria-label="View {att.filename}"
											onclick={() => openLightbox(gi, ai)}
										>
											{#if att.content_type?.startsWith('video/')}
												<span class="thumb-video-badge"><Icon name="play" size={14} label="Video" /></span>
											{/if}
											<img
												src={att.proxy_url || att.url}
												alt={att.filename}
												loading="lazy"
											/>
											<div class="thumb-overlay">
												<span class="thumb-meta">{att.author_name || 'Unknown'}</span>
												{#if att.channel_name}
													<span class="thumb-channel">#{att.channel_name}</span>
												{/if}
											</div>
										</button>
									{/each}
								</div>
							</section>
						{/each}

						{#if timelineHasMore}
							<LoadMore loading={timelineLoading} onclick={loadMoreTimeline}>Load more</LoadMore>
						{/if}
					</div>
				{/if}

				{#if lightboxOpen && lightboxAttachment}
					<Lightbox
						attachment={lightboxAttachment}
						hasPrev={lightboxHasPrev}
						hasNext={lightboxHasNext}
						onclose={() => { lightboxOpen = false; }}
						onprev={() => { if (lightboxHasPrev) lightboxIndex--; }}
						onnext={() => { if (lightboxHasNext) lightboxIndex++; }}
					/>
				{/if}
			{/if}
		</div>
	</div>
</div>

<style>
	.gallery-page {
		height: 100%;
		display: flex;
		overflow: hidden;
	}

	/* ── Sidebar ── */
	.sidebar {
		width: 220px;
		flex-shrink: 0;
		background: var(--bg-surface);
		border-right: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.sidebar-section {
		padding: var(--space-4) var(--space-4) var(--space-3);
		border-bottom: 1px solid var(--border-subtle);
	}

	.sidebar-section--grow {
		flex: 1;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		border-bottom: none;
	}

	.sidebar-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
		margin-bottom: var(--space-2);
	}

	.chip-row {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
	}

	.capitalize {
		text-transform: capitalize;
	}

	/* Channel list */
	.channel-list {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-1) 0;
	}

	.channel-item {
		width: 100%;
		display: flex;
		align-items: center;
		gap: var(--space-2);
		height: 30px;
		padding: 0 var(--space-2);
		border-radius: var(--radius-sm);
		font: var(--type-label-sm);
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

	.channel-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* ── Main content ── */
	.gallery-main {
		flex: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		min-width: 0;
	}

	.gallery-header {
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
		padding: var(--space-4) var(--space-6);
		flex-shrink: 0;
	}

	.header-row {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.header-row h1 {
		font: var(--type-heading-lg);
	}

	.header-meta {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		margin-top: var(--space-1);
	}

	.gallery-body {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-5) var(--space-6);
	}

	.thumb-skeletons {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: var(--space-2);
	}

	/* ── Timeline view ── */
	.timeline {
		display: flex;
		flex-direction: column;
		gap: var(--space-8);
	}

	.timeline-header {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
		margin-bottom: var(--space-4);
		padding-bottom: var(--space-2);
		border-bottom: 1px solid var(--border-subtle);
	}

	.timeline-label {
		font: var(--type-heading-md);
		color: var(--text-primary);
	}

	.timeline-count {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.timeline-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
		gap: var(--space-2);
	}

	.timeline-thumb {
		position: relative;
		aspect-ratio: 1;
		border-radius: var(--radius-sm);
		overflow: hidden;
		background: var(--bg-raised);
		border: 1px solid var(--border-subtle);
		cursor: pointer;
		padding: 0;
		transition:
			border-color var(--duration-micro) var(--ease-out-quint),
			transform var(--duration-micro) var(--ease-out-quint);
	}

	.timeline-thumb:hover {
		border-color: var(--border-strong);
		transform: scale(1.02);
		z-index: 1;
	}

	.timeline-thumb img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.thumb-video-badge {
		position: absolute;
		top: 6px;
		right: 6px;
		width: 28px;
		height: 28px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-full);
		background: rgba(0, 0, 0, 0.7);
		color: var(--text-primary);
		z-index: 2;
	}

	.thumb-overlay {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		padding: var(--space-5) var(--space-2) 6px;
		background: linear-gradient(transparent, rgba(0, 0, 0, 0.75));
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 1px;
		opacity: 0;
		transition: opacity var(--duration-micro) var(--ease-out-quint);
	}

	.timeline-thumb:hover .thumb-overlay { opacity: 1; }

	.thumb-meta {
		font: var(--type-label-xs);
		color: var(--text-primary);
	}

	.thumb-channel {
		font: var(--type-label-xs);
		color: var(--text-secondary);
	}

	/* ── Responsive ── */
	@media (max-width: 768px) {
		.sidebar { display: none; }
		.gallery-body { padding: var(--space-3); }
		.timeline-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
	}
</style>
