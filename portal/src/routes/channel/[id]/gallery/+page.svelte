<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';
	import { getGallery, getGuilds, getGuild } from '#lib/api.ts';
	import type { GalleryAttachment, Channel } from '#lib/types.ts';
	import GalleryGrid from '#lib/components/GalleryGrid.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

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
		<a href="/channel/{channelId}" class="back-link">
			<Icon name="arrow-left" size={14} /> #{channel?.name ?? 'channel'}
		</a>
		<div class="header-title-row">
			<h1>Gallery</h1>
			{#if channel}
				<span class="channel-label">#{channel.name}</span>
			{/if}
		</div>
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
			<div class="thumb-skeletons" aria-busy="true">
				<span class="sr-only" role="status">Loading gallery…</span>
				{#each Array.from({ length: 12 }, (_, i) => i) as i (i)}
					<Skeleton aspect="1" radius="sm" />
				{/each}
			</div>
		{:else if error}
			<Alert tone="danger" title="The gallery could not be loaded">{error}</Alert>
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
		padding: var(--space-4) var(--space-6);
		flex-shrink: 0;
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-label-sm);
		color: var(--text-tertiary);
		margin-bottom: var(--space-2);
	}

	.back-link:hover {
		color: var(--text-primary);
	}

	.header-title-row {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
	}

	.header-title-row h1 {
		font: var(--type-heading-lg);
	}

	.channel-label {
		font: var(--type-label-md);
		color: var(--text-secondary);
	}

	.header-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		margin-top: var(--space-2);
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
</style>
