<script lang="ts">
	import type { GalleryAttachment } from '#lib/types.ts';
	import Icon from './ui/Icon.svelte';
	import IconButton from './ui/IconButton.svelte';

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
		{#if hasPrev}
			<span class="nav-arrow prev">
				<IconButton
					icon="chevron-left"
					label="Previous"
					variant="overlay"
					size="lg"
					onclick={(e) => { e.stopPropagation(); onprev?.(); }}
				/>
			</span>
		{/if}
		{#if hasNext}
			<span class="nav-arrow next">
				<IconButton
					icon="chevron-right"
					label="Next"
					variant="overlay"
					size="lg"
					onclick={(e) => { e.stopPropagation(); onnext?.(); }}
				/>
			</span>
		{/if}

		<span class="close-btn">
			<IconButton icon="x" label="Close" variant="overlay" onclick={onclose} />
		</span>

		<div class="image-frame">
			<img
				src={attachment.proxy_url || attachment.url}
				alt={attachment.filename}
				class="lightbox-img"
			/>
		</div>

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
				><Icon name="arrow-up-right" size={14} /> Open</a>
			</div>
		</div>
	</div>
</div>

<style>
	.lightbox-overlay {
		position: fixed;
		inset: 0;
		z-index: 1000;
		background: rgba(5, 5, 6, 0.96);
		display: flex;
		align-items: center;
		justify-content: center;
		animation: fade-in var(--duration-medium) var(--ease-out-quint);
	}

	.lightbox-content {
		position: relative;
		display: flex;
		flex-direction: column;
		max-width: 95vw;
		max-height: 95vh;
		animation: scale-in var(--duration-medium) var(--ease-out-quint);
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
		box-shadow: var(--shadow-floating);
	}

	.close-btn {
		position: absolute;
		top: -44px;
		right: 0;
		z-index: 10;
	}

	.nav-arrow {
		position: absolute;
		top: 50%;
		translate: 0 -50%;
		z-index: 10;
	}

	.nav-arrow.prev { left: -60px; }
	.nav-arrow.next { right: -60px; }

	.info-bar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-3) var(--space-1);
		margin-top: var(--space-3);
		gap: var(--space-4);
		flex-wrap: wrap;
	}

	.info-left, .info-right {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.info-author {
		font: var(--type-label-sm);
		color: var(--text-secondary);
	}

	.info-filename {
		color: var(--text-secondary);
		max-width: 200px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.info-sep { color: var(--text-tertiary); }

	.open-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		margin-left: var(--space-2);
		font: var(--type-label-sm);
		color: var(--accent);
	}

	@media (max-width: 768px) {
		.nav-arrow.prev { left: 4px; }
		.nav-arrow.next { right: 4px; }
	}
</style>
