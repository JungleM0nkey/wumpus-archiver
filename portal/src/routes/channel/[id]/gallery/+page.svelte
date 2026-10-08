<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';
	import { getGallery, getGuilds, getGuild } from '#lib/api.ts';
	import type { GalleryAttachment, Channel } from '#lib/types.ts';
	import GalleryGrid from '#lib/components/GalleryGrid.svelte';

	let { params }: PageProps = $props();
	const channelId = $derived(params.id);

	let channel: Channel | null = $state(null);
	let attachments: GalleryAttachment[] = $state([]);
	let total = $state(0);
	let loading = $state(true);
	let loadingMore = $state(false);
	let hasMore = $state(false);
	let offset = $state(0);
	let error = $state('');
	const limit = 60;

	onMount(async () => {
		await Promise.all([loadChannel(), loadImages()]);
	});

	async function loadChannel() {
		try {
			const guilds = await getGuilds();
			if (guilds.length > 0) {
				const detail = await getGuild(guilds[0].id);
				channel = detail.channels.find(c => c.id === channelId) ?? null;
			}
		} catch (e) {
			console.error('Failed to load channel info:', e);
		}
	}

	async function loadImages() {
		try {
			const res = await getGallery(channelId, { limit, offset: 0 });
			attachments = res.attachments;
			total = res.total;
			hasMore = res.has_more;
			offset = res.attachments.length;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load gallery';
		} finally {
			loading = false;
		}
	}

	async function loadMore() {
		if (loadingMore || !hasMore) return;
		loadingMore = true;
		try {
			const res = await getGallery(channelId, { limit, offset });
			attachments = [...attachments, ...res.attachments];
			hasMore = res.has_more;
			offset += res.attachments.length;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load more';
		} finally {
			loadingMore = false;
		}
	}
</script>

<div class="gallery-page">
	<header class="gallery-header">
		<a href="/channel/{channelId}" class="back-link mono">← #{channel?.name ?? 'channel'}</a>
		{#if channel}
			<div class="header-title-row">
				<h1>Gallery</h1>
				<span class="channel-label">#{channel.name}</span>
			</div>
		{:else}
			<h1>Gallery</h1>
		{/if}
		<div class="header-meta mono">
			{#if total > 0}
				<span>{total.toLocaleString()} image{total !== 1 ? 's' : ''}</span>
				<span class="sep">·</span>
			{/if}
			<span>{attachments.length.toLocaleString()} loaded</span>
		</div>
	</header>

	<div class="gallery-body">
		{#if loading}
			<div class="center-state">
				<div class="spinner"></div>
				<span class="mono">Loading gallery...</span>
			</div>
		{:else if error}
			<div class="center-state error">⚠ {error}</div>
		{:else}
			<GalleryGrid
				{attachments}
				loading={loadingMore}
				{hasMore}
				onloadmore={loadMore}
			/>
		{/if}
	</div>
</div>

<style>
	.gallery-page {
		height: 100%;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.gallery-header {
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
		padding: var(--space-5) var(--space-6) var(--space-4);
		flex-shrink: 0;
	}

	.back-link {
		display: inline-block;
		font-size: 12px;
		color: var(--text-tertiary);
		text-decoration: none;
		margin-bottom: var(--space-3);
		transition: color var(--duration-micro);
	}

	.back-link:hover { color: var(--accent); }

	.header-title-row {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
	}

	.header-title-row h1 {
		font-size: 28px;
		font-weight: 700;
		letter-spacing: -0.03em;
	}


	.channel-label {
		font-size: 14px;
		color: var(--text-tertiary);
		font-weight: 500;
	}

	.header-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 12px;
		color: var(--text-tertiary);
		margin-top: var(--space-2);
	}

	.sep { color: var(--text-tertiary); }

	.gallery-body {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-5) var(--space-6);
	}

	.center-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-16) 0;
		color: var(--text-secondary);
	}

	.center-state.error { color: var(--danger); }

	.spinner {
		width: 20px; height: 20px;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin { to { transform: rotate(360deg); } }
</style>
