<script lang="ts">
	import type { GalleryAttachment } from '$lib/types';

	let {
		attachment,
		onclose,
		onnext,
		onprev,
		hasPrev = false,
		hasNext = false,
	}: {
		attachment: GalleryAttachment;
		onclose: () => void;
		onnext?: () => void;
		onprev?: () => void;
		hasPrev?: boolean;
		hasNext?: boolean;
	} = $props();

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onclose();
		if (e.key === 'ArrowRight' && hasNext && onnext) onnext();
		if (e.key === 'ArrowLeft' && hasPrev && onprev) onprev();
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatDate(d: string): string {
		return new Date(d).toLocaleDateString('en-US', {
			month: 'short', day: 'numeric', year: 'numeric',
			hour: 'numeric', minute: '2-digit',
		});
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="lightbox-overlay" onclick={onclose}>
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div class="lightbox-content" onclick={(e) => e.stopPropagation()}>
		<!-- Navigation arrows -->
		{#if hasPrev}
			<button class="nav-arrow prev" onclick={(e) => { e.stopPropagation(); onprev?.(); }} aria-label="Previous">
				‹
			</button>
		{/if}
		{#if hasNext}
			<button class="nav-arrow next" onclick={(e) => { e.stopPropagation(); onnext?.(); }} aria-label="Next">
				›
			</button>
		{/if}

		<!-- Close button -->
		<button class="close-btn" onclick={onclose} aria-label="Close">✕</button>

		<!-- Image -->
		<div class="image-frame">
			<img
				src={attachment.proxy_url || attachment.url}
				alt={attachment.filename}
				class="lightbox-img"
			/>
		</div>

		<!-- Info bar -->
		<div class="info-bar">
			<div class="info-left">
				{#if attachment.author_name}
					<span class="info-author">{attachment.author_name}</span>
					<span class="info-sep">·</span>
				{/if}
				<span class="mono info-date">{formatDate(attachment.created_at)}</span>
			</div>
			<div class="info-right mono">
				<span class="info-filename">{attachment.filename}</span>
				<span class="info-sep">·</span>
				{#if attachment.width && attachment.height}
					<span>{attachment.width}×{attachment.height}</span>
					<span class="info-sep">·</span>
				{/if}
				<span>{formatSize(attachment.size)}</span>
				<a
					href={attachment.url}
					target="_blank"
					rel="noopener noreferrer"
					class="open-link"
					onclick={(e) => e.stopPropagation()}
				>↗ Open</a>
			</div>
		</div>
	</div>
</div>

<style>
	.lightbox-overlay {
		position: fixed;
		inset: 0;
		z-index: 1000;
		background: rgba(0, 0, 0, 0.92);
		display: flex;
		align-items: center;
		justify-content: center;
		animation: fadeIn 0.15s ease-out;
	}

	@keyframes fadeIn { from { opacity: 0; } }

	.lightbox-content {
		position: relative;
		display: flex;
		flex-direction: column;
		max-width: 95vw;
		max-height: 95vh;
	}

	.image-frame {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 0;
	}

	.lightbox-img {
		max-width: 90vw;
		max-height: 82vh;
		object-fit: contain;
		border-radius: var(--radius-sm);
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
	}

	.close-btn {
		position: absolute;
		top: -40px;
		right: 0;
		font-size: 20px;
		color: var(--text-muted);
		background: none;
		border: none;
		cursor: pointer;
		padding: 4px 8px;
		border-radius: var(--radius-sm);
		transition: all 0.12s;
		z-index: 10;
	}

	.close-btn:hover {
		color: var(--text-primary);
		background: rgba(255, 255, 255, 0.1);
	}

	.nav-arrow {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		font-size: 48px;
		font-weight: 300;
		color: rgba(255, 255, 255, 0.5);
		background: none;
		border: none;
		cursor: pointer;
		padding: 16px 12px;
		border-radius: var(--radius-md);
		transition: all 0.12s;
		z-index: 10;
		line-height: 1;
	}

	.nav-arrow:hover {
		color: white;
		background: rgba(255, 255, 255, 0.08);
	}

	.nav-arrow.prev { left: -56px; }
	.nav-arrow.next { right: -56px; }

	.info-bar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--sp-3) var(--sp-1);
		margin-top: var(--sp-3);
		gap: var(--sp-4);
		flex-wrap: wrap;
	}

	.info-left, .info-right {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		font-size: 12px;
		color: var(--text-muted);
	}

	.info-author {
		color: var(--text-secondary);
		font-weight: 500;
	}

	.info-filename {
		color: var(--text-secondary);
		max-width: 200px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.info-sep { color: var(--text-faint); }

	.open-link {
		color: var(--accent);
		text-decoration: none;
		font-size: 12px;
		margin-left: var(--sp-2);
		transition: opacity 0.12s;
	}

	.open-link:hover { opacity: 0.8; }

	@media (max-width: 768px) {
		.nav-arrow.prev { left: 4px; }
		.nav-arrow.next { right: 4px; }
		.nav-arrow { font-size: 36px; background: rgba(0,0,0,0.5); }
	}
</style>
