<script lang="ts">
	import { getGuildGallery, getGuildGalleryTimeline } from '$lib/api';
	import type { GalleryAttachment, TimelineGalleryGroup } from '$lib/types';
	import GalleryGrid from './GalleryGrid.svelte';
	import Lightbox from './Lightbox.svelte';

	type ViewMode = 'grid' | 'timeline';
	type GroupBy = 'week' | 'month' | 'year';

	interface Props {
		channelId: string;
		guildId: string;
	}
	let { channelId, guildId }: Props = $props();

	// View state
	let viewMode: ViewMode = $state('grid');
	let groupBy: GroupBy = $state('month');
	let initialized = $state(false);

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

	let loading = $state(true);
	let error = $state('');

	const limit = 60;
	const timelineGroupLimit = 6;

	let totalCount = $derived(viewMode === 'grid' ? gridTotal : timelineTotal);

	// Load on mount via effect
	$effect(() => {
		if (!initialized) {
			initialized = true;
			loadContent();
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
		if (reset) {
			gridAttachments = [];
			gridOffset = 0;
		}
		gridLoading = true;
		try {
			const res = await getGuildGallery(guildId, {
				limit,
				offset: reset ? 0 : gridOffset,
				channel_id: channelId
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
		if (reset) {
			timelineGroups = [];
			timelineOffset = 0;
		}
		timelineLoading = true;
		try {
			const res = await getGuildGalleryTimeline(guildId, {
				limit: timelineGroupLimit,
				offset: reset ? 0 : timelineOffset,
				channel_id: channelId,
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

	function openLightbox(groupIdx: number, imgIdx: number) {
		const group = timelineGroups[groupIdx];
		if (!group) return;
		lightboxAttachments = group.attachments;
		lightboxIndex = imgIdx;
		lightboxOpen = true;
	}
</script>

<div class="channel-gallery">
	<!-- Toolbar -->
	<div class="gallery-toolbar">
		<div class="toolbar-left">
			<div class="view-toggle">
				<button class="toggle-btn" class:active={viewMode === 'grid'} onclick={() => switchView('grid')}>
					<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>
					Grid
				</button>
				<button class="toggle-btn" class:active={viewMode === 'timeline'} onclick={() => switchView('timeline')}>
					<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="14" height="3" rx="1"/><rect x="1" y="6" width="14" height="3" rx="1"/><rect x="1" y="11" width="14" height="3" rx="1"/></svg>
					Timeline
				</button>
			</div>

			{#if viewMode === 'timeline'}
				<div class="group-pills">
					{#each (['week', 'month', 'year'] as const) as g}
						<button class="pill" class:active={groupBy === g} onclick={() => switchGroupBy(g)}>
							{g}
						</button>
					{/each}
				</div>
			{/if}
		</div>

		{#if totalCount > 0}
			<span class="toolbar-count mono">
				{totalCount.toLocaleString()} item{totalCount !== 1 ? 's' : ''}
				{#if viewMode === 'timeline'}&middot; by {groupBy}{/if}
			</span>
		{/if}
	</div>

	<!-- Content -->
	<div class="gallery-content">
		{#if loading}
			<div class="center-state">
				<div class="spinner"></div>
				<span class="mono">Loading gallery...</span>
			</div>
		{:else if error}
			<div class="center-state error-state">
				<span>&#x26A0; {error}</span>
			</div>
		{:else if viewMode === 'grid'}
			{#if gridAttachments.length === 0}
				<div class="center-state muted">
					<div class="empty-icon">🖼</div>
					<span>No images found in this channel.</span>
				</div>
			{:else}
				<GalleryGrid
					attachments={gridAttachments}
					loading={gridLoading}
					hasMore={gridHasMore}
					onloadmore={loadMoreGrid}
				/>
			{/if}
		{:else}
			{#if timelineGroups.length === 0}
				<div class="center-state muted">
					<div class="empty-icon">🖼</div>
					<span>No images found in this channel.</span>
				</div>
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
										onclick={() => openLightbox(gi, ai)}
										aria-label="View {att.filename}"
									>
										{#if att.content_type?.startsWith('video/')}
											<div class="thumb-video-badge">
												<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M6 4l6 4-6 4V4z"/></svg>
											</div>
										{/if}
										<img
											src={att.url}
											alt={att.filename}
											loading="lazy"
										/>
										<div class="thumb-overlay">
											<span class="thumb-meta">{att.author_name || 'Unknown'}</span>
										</div>
									</button>
								{/each}
							</div>
						</section>
					{/each}

					{#if timelineHasMore}
						<div class="load-more-row">
							<button class="load-more-btn" onclick={loadMoreTimeline} disabled={timelineLoading}>
								{#if timelineLoading}
									<div class="spinner small"></div>
									Loading...
								{:else}
									Load more
								{/if}
							</button>
						</div>
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

<style>
	.channel-gallery {
		display: flex;
		flex-direction: column;
		height: 100%;
		overflow: hidden;
	}

	/* ── Toolbar ── */
	.gallery-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--sp-4);
		padding: var(--sp-3) var(--sp-6);
		border-bottom: 1px solid var(--border);
		background: var(--bg-surface);
		flex-shrink: 0;
	}

	.toolbar-left {
		display: flex;
		align-items: center;
		gap: var(--sp-4);
	}

	.toolbar-count {
		font-size: 12px;
		color: var(--text-muted);
		white-space: nowrap;
	}

	/* View toggle */
	.view-toggle {
		display: flex;
		gap: 2px;
		background: var(--bg-base);
		border-radius: var(--radius-sm);
		padding: 2px;
	}

	.toggle-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 5px;
		padding: 5px 10px;
		border-radius: var(--radius-sm);
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
		background: none;
		border: none;
		cursor: pointer;
		transition: all 0.15s;
	}

	.toggle-btn:hover { color: var(--text-primary); }
	.toggle-btn.active { background: var(--bg-hover); color: var(--accent); }

	/* Group pills */
	.group-pills {
		display: flex;
		gap: 4px;
	}

	.pill {
		padding: 4px 10px;
		border-radius: 999px;
		font-size: 11px;
		font-weight: 500;
		text-transform: capitalize;
		color: var(--text-secondary);
		background: var(--bg-base);
		border: 1px solid var(--border);
		cursor: pointer;
		transition: all 0.15s;
	}

	.pill:hover { color: var(--text-primary); border-color: var(--text-faint); }
	.pill.active { background: var(--accent); color: var(--bg-base); border-color: var(--accent); }

	/* ── Content ── */
	.gallery-content {
		flex: 1;
		overflow-y: auto;
		padding: var(--sp-5) var(--sp-6);
	}

	/* ── Center states ── */
	.center-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-16) 0;
		color: var(--text-secondary);
	}

	.error-state { color: var(--error); }
	.muted { color: var(--text-muted); }

	.empty-icon {
		font-size: 48px;
		opacity: 0.5;
	}

	.spinner {
		width: 20px;
		height: 20px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.spinner.small {
		width: 14px;
		height: 14px;
		border-width: 1.5px;
	}

	@keyframes spin { to { transform: rotate(360deg); } }

	/* ── Timeline view ── */
	.timeline {
		display: flex;
		flex-direction: column;
		gap: var(--sp-8);
	}

	.timeline-header {
		display: flex;
		align-items: baseline;
		gap: var(--sp-3);
		margin-bottom: var(--sp-4);
		padding-bottom: var(--sp-2);
		border-bottom: 1px solid var(--border);
	}

	.timeline-label {
		font-size: 18px;
		font-weight: 600;
		letter-spacing: -0.02em;
		color: var(--text-primary);
	}

	.timeline-count {
		font-size: 12px;
		color: var(--text-muted);
	}

	.timeline-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
		gap: var(--sp-2);
	}

	.timeline-thumb {
		position: relative;
		aspect-ratio: 1;
		border-radius: var(--radius-sm);
		overflow: hidden;
		background: var(--bg-base);
		border: 1px solid var(--border);
		cursor: pointer;
		padding: 0;
		transition: border-color 0.15s, transform 0.15s;
	}

	.timeline-thumb:hover {
		border-color: var(--accent);
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
		background: rgba(0, 0, 0, 0.7);
		border-radius: 50%;
		width: 28px;
		height: 28px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: white;
		z-index: 2;
	}

	.thumb-overlay {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		padding: 20px 8px 6px;
		background: linear-gradient(transparent, rgba(0, 0, 0, 0.75));
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 1px;
		opacity: 0;
		transition: opacity 0.15s;
	}

	.timeline-thumb:hover .thumb-overlay { opacity: 1; }

	.thumb-meta {
		font-size: 11px;
		color: #fff;
		font-weight: 500;
	}

	/* Load more */
	.load-more-row {
		display: flex;
		justify-content: center;
		padding: var(--sp-4) 0 var(--sp-8);
	}

	.load-more-btn {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: 8px 24px;
		border-radius: var(--radius-sm);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		cursor: pointer;
		transition: all 0.15s;
	}

	.load-more-btn:hover:not(:disabled) {
		border-color: var(--accent);
		color: var(--accent);
	}

	.load-more-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	/* ── Responsive ── */
	@media (max-width: 768px) {
		.gallery-content { padding: var(--sp-3); }
		.gallery-toolbar { padding: var(--sp-3); }
		.timeline-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
	}
</style>
