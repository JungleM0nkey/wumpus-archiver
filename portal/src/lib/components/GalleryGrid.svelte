<script lang="ts">
	import type { GalleryAttachment } from '#lib/types.ts';
	import Lightbox from './Lightbox.svelte';
	import LoadMore from './LoadMore.svelte';
	import EmptyState from './ui/EmptyState.svelte';

	let {
		attachments = [],
		loading = false,
		hasMore = false,
		onloadmore,
	}: {
		attachments: GalleryAttachment[];
		loading?: boolean;
		hasMore?: boolean;
		onloadmore?: () => void;
	} = $props();

	let selectedIndex: number | null = $state(null);

	function openLightbox(index: number) {
		selectedIndex = index;
	}

	function closeLightbox() {
		selectedIndex = null;
	}

	function nextImage() {
		if (selectedIndex !== null && selectedIndex < attachments.length - 1) {
			selectedIndex++;
		}
	}

	function prevImage() {
		if (selectedIndex !== null && selectedIndex > 0) {
			selectedIndex--;
		}
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function thumbUrl(att: GalleryAttachment): string {
		// Use proxy URL for thumbnails and add size params if CDN supports it
		const base = att.proxy_url || att.url;
		if (base.includes('cdn.discordapp.com') || base.includes('media.discordapp.net')) {
			return `${base}?width=300&height=300`;
		}
		return base;
	}

	// Aspect ratio for masonry-like layout
	function aspectClass(att: GalleryAttachment): string {
		if (!att.width || !att.height) return '';
		const ratio = att.width / att.height;
		if (ratio > 1.8) return 'wide';
		if (ratio < 0.6) return 'tall';
		return '';
	}
</script>

{#if attachments.length === 0 && !loading}
	<EmptyState icon="image-off" title="No images in this channel." />
{:else}
	<div class="gallery-grid">
		{#each attachments as att, i (att.id)}
			<button
				class="gallery-thumb {aspectClass(att)}"
				onclick={() => openLightbox(i)}
				aria-label="View {att.filename}"
			>
				<img
					src={thumbUrl(att)}
					alt={att.filename}
					loading="lazy"
					class="thumb-img"
				/>
				<div class="thumb-overlay">
					<span class="thumb-filename">{att.filename}</span>
					<span class="thumb-meta mono">{formatSize(att.size)}</span>
				</div>
			</button>
		{/each}
	</div>

	{#if hasMore && onloadmore}
		<LoadMore {loading} onclick={onloadmore}>Load more images</LoadMore>
	{/if}
{/if}

{#if selectedIndex !== null}
	<Lightbox
		attachment={attachments[selectedIndex]}
		onclose={closeLightbox}
		onnext={nextImage}
		onprev={prevImage}
		hasPrev={selectedIndex > 0}
		hasNext={selectedIndex < attachments.length - 1}
	/>
{/if}

<style>
	.gallery-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: var(--space-2);
	}

	.gallery-thumb {
		position: relative;
		aspect-ratio: 1;
		overflow: hidden;
		border-radius: var(--radius-sm);
		border: 1px solid var(--border-subtle);
		background: var(--bg-raised);
		cursor: pointer;
		padding: 0;
		transition:
			border-color var(--duration-micro) var(--ease-out-quint),
			transform var(--duration-micro) var(--ease-out-quint);
	}

	.gallery-thumb:hover {
		border-color: var(--border-strong);
		transform: scale(1.02);
		z-index: 2;
	}

	.gallery-thumb.wide {
		grid-column: span 2;
		aspect-ratio: 2;
	}

	.gallery-thumb.tall {
		grid-row: span 2;
		aspect-ratio: auto;
	}

	.thumb-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.thumb-overlay {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		padding: var(--space-4) var(--space-2) var(--space-2);
		background: linear-gradient(transparent, rgba(0, 0, 0, 0.75));
		display: flex;
		flex-direction: column;
		gap: 2px;
		opacity: 0;
		transition: opacity var(--duration-micro) var(--ease-out-quint);
	}

	.gallery-thumb:hover .thumb-overlay {
		opacity: 1;
	}

	.thumb-filename {
		font: var(--type-label-xs);
		color: rgba(255, 255, 255, 0.9);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.thumb-meta {
		font: var(--type-mono-sm);
		color: rgba(255, 255, 255, 0.6);
	}

	@media (max-width: 600px) {
		.gallery-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
		.gallery-thumb.wide { grid-column: span 1; aspect-ratio: 1; }
		.gallery-thumb.tall { grid-row: span 1; }
	}
</style>
