<script lang="ts">
	import type { GalleryAttachment } from '#lib/types.ts';
	import Lightbox from './Lightbox.svelte';

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
	<div class="empty-gallery">
		<div class="empty-icon">🖼</div>
		<span>No images in this channel.</span>
	</div>
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

	{#if hasMore}
		<div class="load-more">
			<button class="load-more-btn" onclick={onloadmore} disabled={loading}>
				{#if loading}
					<span class="spinner"></span> Loading...
				{:else}
					Load more images
				{/if}
			</button>
		</div>
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
		border-radius: var(--radius-xs);
		border: 1px solid var(--border-subtle);
		background: var(--bg-raised);
		cursor: pointer;
		padding: 0;
		transition: all var(--duration-micro) var(--ease-out-quint);
	}

	.gallery-thumb:hover {
		border-color: var(--accent);
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
		transition: opacity var(--duration-micro);
	}

	.gallery-thumb:hover .thumb-overlay {
		opacity: 1;
	}

	.thumb-filename {
		font-size: 11px;
		color: rgba(255, 255, 255, 0.9);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.thumb-meta {
		font-size: 10px;
		color: rgba(255, 255, 255, 0.6);
	}

	.empty-gallery {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-16) 0;
		color: var(--text-secondary);
	}

	.empty-icon {
		font-size: 48px;
		opacity: 0.5;
	}

	.load-more {
		display: flex;
		justify-content: center;
		padding: var(--space-6) 0;
	}

	.load-more-btn {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--text-secondary);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		padding: var(--space-2) var(--space-5);
		cursor: pointer;
		transition: all var(--duration-micro) var(--ease-out-quint);
	}

	.load-more-btn:hover:not(:disabled) {
		border-color: var(--accent);
		color: var(--accent);
	}

	.load-more-btn:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.spinner {
		width: 14px; height: 14px;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		display: inline-block;
	}

	@keyframes spin { to { transform: rotate(360deg); } }

	@media (max-width: 600px) {
		.gallery-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
		.gallery-thumb.wide { grid-column: span 1; aspect-ratio: 1; }
		.gallery-thumb.tall { grid-row: span 1; }
	}
</style>
