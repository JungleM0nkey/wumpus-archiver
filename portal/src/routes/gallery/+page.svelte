<script lang="ts">
	import { onMount } from 'svelte';
	import { getGuilds, getGuild, getGuildGallery, getGuildGalleryTimeline } from '$lib/api';
	import type { GalleryAttachment, Channel, GuildDetail, TimelineGalleryGroup } from '$lib/types';
	import { ChannelType } from '$lib/types';
	import GalleryGrid from '$lib/components/GalleryGrid.svelte';
	import Lightbox from '$lib/components/Lightbox.svelte';

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

	function formatFileSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	let totalCount = $derived(viewMode === 'grid' ? gridTotal : timelineTotal);
</script>

<div class="gallery-page">
	<aside class="sidebar">
		<!-- View mode tabs -->
		<div class="sidebar-section">
			<h3 class="sidebar-label">View</h3>
			<div class="tab-group">
				<button class="tab" class:active={viewMode === 'grid'} onclick={() => switchView('grid')}>
					<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>
					Grid
				</button>
				<button class="tab" class:active={viewMode === 'timeline'} onclick={() => switchView('timeline')}>
					<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="14" height="3" rx="1"/><rect x="1" y="6" width="14" height="3" rx="1"/><rect x="1" y="11" width="14" height="3" rx="1"/></svg>
					Timeline
				</button>
			</div>
		</div>

		<!-- Group by (timeline only) -->
		{#if viewMode === 'timeline'}
			<div class="sidebar-section">
				<h3 class="sidebar-label">Group by</h3>
				<div class="pill-group">
					{#each (['week', 'month', 'year'] as const) as g}
						<button class="pill" class:active={groupBy === g} onclick={() => switchGroupBy(g)}>
							{g}
						</button>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Channel filter -->
		<div class="sidebar-section sidebar-section--grow">
			<h3 class="sidebar-label">Channels</h3>
			<div class="channel-list">
				<button
					class="channel-item"
					class:active={selectedChannel === null}
					onclick={() => filterChannel(null)}
				>
					<span class="channel-icon">*</span>
					<span class="channel-name">All channels</span>
				</button>
				{#each channels as ch (ch.id)}
					<button
						class="channel-item"
						class:active={selectedChannel === ch.id}
						onclick={() => filterChannel(ch.id)}
					>
						<span class="channel-icon">#</span>
						<span class="channel-name">{ch.name}</span>
					</button>
				{/each}
			</div>
		</div>
	</aside>

	<div class="gallery-main">
		<header class="gallery-header">
			<div class="header-row">
				<h1 class="serif">Gallery<span class="dot">.</span></h1>
				{#if selectedChannel}
					{@const ch = channels.find(c => c.id === selectedChannel)}
					{#if ch}
						<span class="channel-badge">#{ch.name}</span>
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
				<div class="center-state">
					<div class="spinner"></div>
					<span class="mono">Loading gallery...</span>
				</div>
			{:else if error}
				<div class="center-state error-state">
					<span>&#x26A0; {error}</span>
				</div>
			{:else if viewMode === 'grid'}
				<!-- Grid view -->
				{#if gridAttachments.length === 0}
					<div class="center-state muted">
						<span>No images found{selectedChannel ? ' in this channel' : ''}.</span>
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
				<!-- Timeline view -->
				{#if timelineGroups.length === 0}
					<div class="center-state muted">
						<span>No images found{selectedChannel ? ' in this channel' : ''}.</span>
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
										>
											{#if att.content_type?.startsWith('video/')}
												<div class="thumb-video-badge">
													<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M6 4l6 4-6 4V4z"/></svg>
												</div>
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
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.sidebar-section {
		padding: var(--sp-4) var(--sp-4) var(--sp-3);
		border-bottom: 1px solid var(--border);
	}

	.sidebar-section--grow {
		flex: 1;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		border-bottom: none;
	}

	.sidebar-label {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-muted);
		font-weight: 600;
		margin-bottom: var(--sp-2);
	}

	/* Tab buttons */
	.tab-group {
		display: flex;
		gap: 2px;
		background: var(--bg-base);
		border-radius: var(--radius-sm);
		padding: 2px;
	}

	.tab {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 5px;
		padding: 6px 8px;
		border-radius: var(--radius-sm);
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
		background: none;
		border: none;
		cursor: pointer;
		transition: all 0.15s;
	}

	.tab:hover { color: var(--text-primary); }
	.tab.active { background: var(--bg-hover); color: var(--accent); }

	/* Pill group */
	.pill-group {
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

	/* Channel list */
	.channel-list {
		flex: 1;
		overflow-y: auto;
		padding: var(--sp-1) 0;
	}

	.channel-item {
		width: 100%;
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: 5px var(--sp-3);
		border-radius: var(--radius-sm);
		font-size: 12px;
		color: var(--text-secondary);
		text-align: left;
		cursor: pointer;
		transition: all 0.1s;
		background: none;
		border: none;
	}

	.channel-item:hover { background: var(--bg-hover); color: var(--text-primary); }
	.channel-item.active { background: var(--bg-hover); color: var(--accent); }

	.channel-icon {
		color: var(--text-faint);
		font-weight: 700;
		flex-shrink: 0;
		font-size: 13px;
		width: 14px;
		text-align: center;
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
	}

	.gallery-header {
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border);
		padding: var(--sp-5) var(--sp-6) var(--sp-4);
		flex-shrink: 0;
	}

	.header-row {
		display: flex;
		align-items: baseline;
		gap: var(--sp-3);
	}

	.header-row h1 {
		font-size: 28px;
		font-weight: 700;
		letter-spacing: -0.03em;
	}

	.dot { color: var(--accent); }

	.channel-badge {
		font-size: 13px;
		color: var(--accent);
		background: color-mix(in srgb, var(--accent) 12%, transparent);
		padding: 2px 8px;
		border-radius: 999px;
		font-weight: 500;
	}

	.header-meta {
		font-size: 12px;
		color: var(--text-muted);
		margin-top: var(--sp-2);
	}

	.gallery-body {
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

	.timeline-group {}

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

	.thumb-channel {
		font-size: 10px;
		color: rgba(255, 255, 255, 0.6);
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
		.sidebar { display: none; }
		.gallery-body { padding: var(--sp-3); }
		.timeline-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
	}
</style>
