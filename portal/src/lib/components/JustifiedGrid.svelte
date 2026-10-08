<!--
	Attachments as natural-aspect tiles in justified rows: every row fills `width`, as
	near `targetHeight` px tall as its tiles allow. Videos and GIFs carry a badge. A
	local attachment is shown from the portal, any other from Discord. An attachment
	with no recorded size starts square and takes its real shape once it loads.
-->
<script lang="ts">
	import { SvelteMap } from 'svelte/reactivity';
	import { aspectOf, justify, mediaKind } from '#lib/media.ts';
	import type { GalleryAttachment } from '#lib/types.ts';
	import Icon from './ui/Icon.svelte';

	let {
		attachments,
		width,
		targetHeight = 180,
		gap = 4,
		onopen
	}: {
		attachments: GalleryAttachment[];
		/** The width the rows fill, in px. */
		width: number;
		targetHeight?: number;
		gap?: number;
		/** A tile was chosen; `tile` is its element, for the Lightbox to zoom from and return focus to. */
		onopen: (attachment: GalleryAttachment, tile: HTMLElement) => void;
	} = $props();

	/** Aspect ratios measured in the browser, for attachments without a recorded size. */
	const measured = new SvelteMap<string, number>();

	const aspects = $derived(attachments.map((a) => aspectOf(a, measured.get(a.id))));
	const rows = $derived(justify(aspects, width, targetHeight, gap));

	function measure(attachment: GalleryAttachment, w: number, h: number) {
		if (attachment.width && attachment.height) return;
		if (w > 0 && h > 0) measured.set(attachment.id, w / h);
	}

	/** Where a tile's media is: the portal for a local attachment, else Discord's media proxy. */
	function src(attachment: GalleryAttachment): string {
		return attachment.proxy_url || attachment.url;
	}

	const kindLabel = { image: 'Image', gif: 'GIF', video: 'Video' } as const;
</script>

<div class="justified" style:--gap="{gap}px">
	{#each rows as row (row.start)}
		<div class="row" style:height="{row.height}px">
			{#each attachments.slice(row.start, row.end) as attachment, i (attachment.id)}
				{@const kind = mediaKind(attachment)}
				<button
					type="button"
					class="tile"
					data-kind={kind}
					data-attachment-id={attachment.id}
					style:width="{Math.floor(aspects[row.start + i] * row.height * 100) / 100}px"
					aria-label="{kindLabel[kind]}: {attachment.filename}"
					onclick={(e) => onopen(attachment, e.currentTarget)}
				>
					{#if kind === 'video'}
						<video
							src={src(attachment)}
							preload="metadata"
							muted
							playsinline
							tabindex="-1"
							onloadedmetadata={(e) =>
								measure(attachment, e.currentTarget.videoWidth, e.currentTarget.videoHeight)}
						></video>
					{:else}
						<img
							src={src(attachment)}
							alt={attachment.filename}
							loading="lazy"
							onload={(e) => {
								const img = e.currentTarget as HTMLImageElement;
								measure(attachment, img.naturalWidth, img.naturalHeight);
							}}
						/>
					{/if}
					{#if kind === 'video'}
						<span class="kind-badge"><Icon name="play" size={14} /> Video</span>
					{:else if kind === 'gif'}
						<span class="kind-badge">GIF</span>
					{/if}
					<span class="overlay">
						<span class="overlay-author">{attachment.author_name || 'Unknown'}</span>
						{#if attachment.channel_name}
							<span class="overlay-channel">#{attachment.channel_name}</span>
						{/if}
					</span>
				</button>
			{/each}
		</div>
	{/each}
</div>

<style>
	.justified {
		display: flex;
		flex-direction: column;
		gap: var(--gap);
	}

	.row {
		display: flex;
		gap: var(--gap);
	}

	.tile {
		position: relative;
		flex: 0 1 auto;
		min-width: 0;
		height: 100%;
		padding: 0;
		overflow: hidden;
		border-radius: var(--radius-xs);
		background: var(--bg-raised);
		transition: transform var(--duration-micro) var(--ease-out-quint);
	}

	.tile:hover {
		transform: scale(1.02);
		z-index: 1;
	}

	.tile img,
	.tile video {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
		pointer-events: none;
	}

	.kind-badge {
		position: absolute;
		top: var(--space-1);
		left: var(--space-1);
		display: inline-flex;
		align-items: center;
		gap: 3px;
		height: 18px;
		padding: 0 6px;
		border-radius: var(--radius-xs);
		background: rgba(0, 0, 0, 0.66);
		color: #fff;
		font: var(--type-label-xs);
		letter-spacing: 0.02em;
	}

	.overlay {
		position: absolute;
		inset: auto 0 0 0;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 1px;
		padding: var(--space-5) var(--space-2) 6px;
		background: linear-gradient(transparent, rgba(0, 0, 0, 0.75));
		text-align: left;
		opacity: 0;
		transition: opacity var(--duration-micro) var(--ease-out-quint);
	}

	.tile:hover .overlay,
	.tile:focus-visible .overlay {
		opacity: 1;
	}

	.overlay-author {
		font: var(--type-label-xs);
		color: #fff;
	}

	.overlay-channel {
		font: var(--type-label-xs);
		color: rgba(255, 255, 255, 0.7);
	}
</style>
