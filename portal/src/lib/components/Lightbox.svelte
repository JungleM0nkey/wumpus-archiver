<!--
	The Lightbox: the one place an attachment is seen large, for the Media screen and
	Browse's Media tab alike. A screen renders one over the attachments it has loaded and
	calls `open(attachment, tile)` when a tile is chosen; the Lightbox keeps everything
	else to itself.

	It is a modal dialog: the page behind it is inert, so focus stays inside, and Esc
	closes it and returns focus to the tile it opened from. The top bar carries the
	author and a counter; the left and right arrow keys and buttons step through the
	attachments, as does the filmstrip along the bottom; the file's details sit beside
	the media. "Open in conversation" opens the attachment's message in Browse.

	Motion: the media zooms from its tile and back (a view transition), while the scrim
	fades in and the chrome follows 80ms later. Without the View Transitions API, and
	under reduced motion, it only fades.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { mediaKind } from '#lib/media.ts';
	import { channelHref } from '#lib/routes.ts';
	import type { GalleryAttachment } from '#lib/types.ts';
	import Avatar from './ui/Avatar.svelte';
	import Icon from './ui/Icon.svelte';
	import IconButton from './ui/IconButton.svelte';

	let {
		attachments,
		total,
		onnearend
	}: {
		/** The attachments the screen has loaded, in its order. */
		attachments: GalleryAttachment[];
		/** How many there are in all, loaded or not: the counter's "of". */
		total?: number;
		/** Stepping came near the last loaded attachment: a screen that pages loads the next page. */
		onnearend?: () => void;
	} = $props();

	/** The name the zooming media takes for the view transition. */
	const ZOOM_NAME = 'lightbox-media';
	/** Set on <html> while the Lightbox zooms, so the page's own cross-fade stands still. */
	const ZOOMING_CLASS = 'lightbox-zooming';
	/** How close to the last loaded attachment stepping asks for more. */
	const NEAR_END = 3;

	let currentId: string | null = $state(null);
	const index = $derived(currentId === null ? -1 : attachments.findIndex((a) => a.id === currentId));
	const current = $derived(index >= 0 ? attachments[index] : null);
	const kind = $derived(current ? mediaKind(current) : 'image');
	const count = $derived(Math.max(total ?? 0, attachments.length));

	/** The tile the Lightbox opened from, and its attachment, for focus and the zoom back. */
	let opener: HTMLElement | null = null;
	let openerId: string | null = null;
	/** The open or close under way: a second click is ignored, and Esc waits its turn. */
	let busy: Promise<void> | null = null;

	let dialog: HTMLDialogElement | undefined = $state();
	let media: HTMLImageElement | HTMLVideoElement | undefined = $state();
	let strip: HTMLElement | undefined = $state();

	/** Sizes measured in the browser, for attachments without a recorded one. */
	const measured = new SvelteMap<string, [number, number]>();
	const size = $derived.by((): [number, number] | null => {
		if (!current) return null;
		if (current.width && current.height) return [current.width, current.height];
		return measured.get(current.id) ?? null;
	});

	// Attachments the screen no longer has (a filter changed) take the Lightbox with them.
	$effect(() => {
		if (currentId !== null && index < 0) {
			currentId = null;
			opener = null;
		}
	});

	// Keep the current attachment's thumbnail in view in the filmstrip.
	$effect(() => {
		if (!strip || index < 0) return;
		const thumb = strip.querySelector<HTMLElement>(`[data-index="${index}"]`);
		thumb?.scrollIntoView({ block: 'nearest', inline: 'center' });
	});

	/** Open on `attachment`, zooming from `tile` (its grid tile) when given. */
	export async function open(attachment: GalleryAttachment, tile?: HTMLElement): Promise<void> {
		if (currentId !== null || busy) return;
		opener = tile ?? null;
		openerId = attachment.id;
		busy = transition(tile ? mediaIn(tile) : null, async () => {
			currentId = attachment.id;
			await tick();
			dialog?.showModal();
			dialog?.focus();
			return media ?? null;
		});
		try {
			await busy;
		} finally {
			busy = null;
		}
		if (index >= attachments.length - NEAR_END) onnearend?.();
	}

	/** Close, zooming back to the tile it opened from when it still shows that attachment. */
	export async function close(): Promise<void> {
		// The dialog is open, and takes keys, before its zoom in ends: an Esc then closes
		// it once the zoom is done, rather than being lost.
		while (busy) await busy.catch(() => {});
		if (currentId === null) return;
		const tile = openerTile();
		const back = tile && currentId === openerId ? mediaIn(tile) : null;
		busy = transition(back ? (media ?? null) : null, async () => {
			currentId = null;
			await tick();
			return back;
		});
		try {
			await busy;
		} finally {
			busy = null;
		}
		opener = null;
		tile?.focus();
	}

	/** Show the attachment at `i`, if there is one. */
	function show(i: number) {
		if (i < 0 || i >= attachments.length) return;
		currentId = attachments[i].id;
		if (i >= attachments.length - NEAR_END) onnearend?.();
	}

	/** The tile it opened from, or the one that shows its attachment now that the grid redrew. */
	function openerTile(): HTMLElement | null {
		if (opener?.isConnected) return opener;
		if (!openerId) return null;
		return document.querySelector<HTMLElement>(`.tile[data-attachment-id="${CSS.escape(openerId)}"]`);
	}

	function mediaIn(tile: HTMLElement): HTMLElement | null {
		return tile.querySelector<HTMLElement>('img, video');
	}

	function canZoom(): boolean {
		return (
			typeof document.startViewTransition === 'function' &&
			!matchMedia('(prefers-reduced-motion: reduce)').matches
		);
	}

	/**
	 * Run `update` inside a view transition that morphs `from` into the element `update`
	 * returns. Without a `from` the change only fades (the dialog fades itself in and out).
	 */
	async function transition(
		from: HTMLElement | null,
		update: () => Promise<HTMLElement | null>
	): Promise<void> {
		if (!canZoom()) {
			await update();
			return;
		}
		const root = document.documentElement;
		root.classList.add(ZOOMING_CLASS);
		if (from) from.style.viewTransitionName = ZOOM_NAME;
		let to: HTMLElement | null = null;
		const zoom = document.startViewTransition(async () => {
			if (from) from.style.viewTransitionName = '';
			to = await update();
			if (from && to) {
				await decoded(to);
				to.style.viewTransitionName = ZOOM_NAME;
			}
		});
		// A newer transition (a navigation, say) skips this one; nothing is lost.
		zoom.ready.catch(() => {});
		void zoom.finished
			.catch(() => {})
			.finally(() => {
				root.classList.remove(ZOOMING_CLASS);
				if (to) to.style.viewTransitionName = '';
				if (from) from.style.viewTransitionName = '';
			});
		await zoom.updateCallbackDone.catch(() => {});
	}

	/** Wait briefly for an image to decode, so the zoom lands on the picture, not an empty box. */
	async function decoded(element: HTMLElement): Promise<void> {
		if (!(element instanceof HTMLImageElement)) return;
		await Promise.race([
			element.decode().catch(() => {}),
			new Promise((resolve) => setTimeout(resolve, 150))
		]);
	}

	/** The controls Tab moves between, in order. */
	function focusables(): HTMLElement[] {
		if (!dialog) return [];
		return [
			...dialog.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), video[controls]')
		].filter((el) => el.tabIndex >= 0);
	}

	/** Tab wraps around inside the dialog rather than leaving it for the browser's own UI. */
	function trapTab(event: KeyboardEvent) {
		const items = focusables();
		if (items.length === 0) return;
		const first = items[0];
		const last = items[items.length - 1];
		const active = document.activeElement;
		const outside = !active || !items.includes(active as HTMLElement);
		if (event.shiftKey && (active === first || outside)) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && (active === last || outside)) {
			event.preventDefault();
			first.focus();
		}
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Tab') {
			trapTab(event);
			return;
		}
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			void close();
			return;
		}
		if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
		// The video's own controls seek with the arrows.
		if (event.target instanceof HTMLVideoElement) return;
		event.preventDefault();
		event.stopPropagation();
		show(index + (event.key === 'ArrowRight' ? 1 : -1));
	}

	/** Another close request (a platform back gesture): close our way, focus and all. */
	function oncancel(event: Event) {
		event.preventDefault();
		void close();
	}

	function measure(attachment: GalleryAttachment, width: number, height: number) {
		if (attachment.width && attachment.height) return;
		if (width > 0 && height > 0) measured.set(attachment.id, [width, height]);
	}

	function src(attachment: GalleryAttachment): string {
		return attachment.proxy_url || attachment.url;
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	const kindLabel = { image: 'Image', gif: 'GIF', video: 'Video' } as const;
</script>

{#if current}
	<dialog
		bind:this={dialog}
		class="lightbox"
		aria-label="{kindLabel[kind]}: {current.filename}"
		tabindex="-1"
		{onkeydown}
		{oncancel}
	>
		<header class="top-bar chrome">
			<div class="who">
				<Avatar src={current.author_avatar_url} name={current.author_name || 'Unknown'} size={32} />
				<div class="who-text">
					<span class="author">{current.author_name || 'Unknown'}</span>
					<span class="where mono">
						{[current.channel_name && `#${current.channel_name}`, formatDate(current.created_at)]
							.filter(Boolean)
							.join(' · ')}
					</span>
				</div>
			</div>
			<span class="counter mono" aria-live="polite">{index + 1} of {count.toLocaleString()}</span>
			<div class="actions">
				{#if current.channel_id}
					<a class="conversation" href={channelHref(current.channel_id, { message: current.message_id })}>
						<Icon name="message" size={14} /> Open in conversation
					</a>
				{/if}
				<a
					class="original"
					href={current.url}
					target="_blank"
					rel="noopener noreferrer"
					aria-label="Open the original"
					title="Open the original"
				>
					<Icon name="arrow-up-right" size={16} />
				</a>
				<IconButton icon="x" label="Close" variant="overlay" onclick={() => void close()} />
			</div>
		</header>

		<div class="stage">
			{#key current.id}
				{#if kind === 'video'}
					<!-- svelte-ignore a11y_media_has_caption -->
					<video
						bind:this={media}
						class="media"
						class:sized={size}
						style:--aspect={size ? size[0] / size[1] : undefined}
						src={src(current)}
						controls
						playsinline
						preload="metadata"
						onloadedmetadata={(e) =>
							current && measure(current, e.currentTarget.videoWidth, e.currentTarget.videoHeight)}
					></video>
				{:else}
					<img
						bind:this={media}
						class="media"
						class:sized={size}
						style:--aspect={size ? size[0] / size[1] : undefined}
						src={src(current)}
						alt={current.filename}
						onload={(e) => {
							const img = e.currentTarget as HTMLImageElement;
							if (current) measure(current, img.naturalWidth, img.naturalHeight);
						}}
					/>
				{/if}
			{/key}
			<span class="step prev">
				<IconButton
					icon="chevron-left"
					label="Previous"
					variant="overlay"
					size="lg"
					disabled={index <= 0}
					onclick={() => show(index - 1)}
				/>
			</span>
			<span class="step next">
				<IconButton
					icon="chevron-right"
					label="Next"
					variant="overlay"
					size="lg"
					disabled={index >= attachments.length - 1}
					onclick={() => show(index + 1)}
				/>
			</span>
		</div>

		<aside class="details chrome" aria-label="File details">
			<h2 class="file-name">{current.filename}</h2>
			<dl class="meta">
				<div><dt>Size</dt><dd class="mono">{formatSize(current.size)}</dd></div>
				<div>
					<dt>Dimensions</dt>
					<dd class="mono">{size ? `${size[0]} × ${size[1]}` : 'Unknown'}</dd>
				</div>
				<div><dt>Type</dt><dd class="mono">{current.content_type || 'Unknown'}</dd></div>
				<div><dt>Posted</dt><dd class="mono">{formatDate(current.created_at)}</dd></div>
			</dl>
		</aside>

		<nav class="filmstrip chrome" aria-label="Filmstrip" bind:this={strip}>
			{#each attachments as attachment, i (attachment.id)}
				{@const thumbKind = mediaKind(attachment)}
				<button
					type="button"
					class="thumb"
					data-index={i}
					aria-label="{kindLabel[thumbKind]} {i + 1}: {attachment.filename}"
					aria-current={i === index ? 'true' : undefined}
					onclick={() => show(i)}
				>
					{#if thumbKind === 'video'}
						<video src={src(attachment)} preload="metadata" muted playsinline tabindex="-1"></video>
						<span class="thumb-badge"><Icon name="play" size={14} /></span>
					{:else}
						<img src={src(attachment)} alt="" loading="lazy" />
					{/if}
				</button>
			{/each}
		</nav>
	</dialog>
{/if}

<style>
	/* The dialog is the scrim: it fills the viewport, so it fades in as one with its chrome. */
	.lightbox {
		position: fixed;
		inset: 0;
		width: 100vw;
		height: 100dvh;
		max-width: none;
		max-height: none;
		margin: 0;
		padding: 0;
		border: 0;
		outline: none;
		background: rgba(5, 5, 6, 0.98);
		color: var(--text-primary);
		display: grid;
		grid-template:
			'top top' auto
			'stage details' minmax(0, 1fr)
			'strip strip' auto
			/ minmax(0, 1fr) 280px;
		overflow: hidden;
		view-transition-name: lightbox;
		animation: fade-in var(--duration-medium) var(--ease-out-quint);
	}

	.lightbox::backdrop {
		background: transparent;
	}

	/* The chrome follows the scrim in, 80ms later. */
	.chrome {
		animation: enter var(--duration-medium) var(--ease-out-quint) 80ms both;
	}

	.top-bar {
		grid-area: top;
		--enter-rise: -8px;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
		align-items: center;
		gap: var(--space-4);
		min-height: var(--size-topbar);
		padding: var(--space-2) var(--space-4);
	}

	.who {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		min-width: 0;
	}

	.who-text {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.author {
		font: var(--type-label-md);
		color: var(--text-primary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.where {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.counter {
		font: var(--type-mono-sm);
		color: var(--text-secondary);
	}

	.actions {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: var(--space-2);
	}

	.conversation {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		height: 32px;
		padding: 0 var(--space-3);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		background: var(--bg-raised);
		color: var(--text-primary);
		font: var(--type-label-sm);
		white-space: nowrap;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint);
	}

	.conversation:hover {
		background: var(--bg-overlay);
		border-color: var(--border-strong);
		color: var(--text-primary);
	}

	.original {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: var(--radius-sm);
		background: rgba(0, 0, 0, 0.45);
		color: var(--text-primary);
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.original:hover {
		background: rgba(0, 0, 0, 0.7);
		color: var(--text-primary);
	}

	/* The media fills as much of the stage as its shape allows, centred. */
	.stage {
		grid-area: stage;
		position: relative;
		container-type: size;
		display: grid;
		place-items: center;
		min-height: 0;
		padding: var(--space-2) 72px;
	}

	.media {
		display: block;
		max-width: 100%;
		max-height: 100%;
		border-radius: var(--radius-sm);
		box-shadow: var(--shadow-floating);
		background: var(--bg-raised);
	}

	.media.sized {
		width: min(100cqw, 100cqh * var(--aspect));
		height: auto;
		aspect-ratio: var(--aspect);
		object-fit: contain;
	}

	.step {
		position: absolute;
		top: 50%;
		translate: 0 -50%;
	}

	.step.prev {
		left: var(--space-3);
	}

	.step.next {
		right: var(--space-3);
	}

	.details {
		grid-area: details;
		--enter-rise: 0px;
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		min-width: 0;
		padding: var(--space-4);
		border-left: 1px solid var(--border-subtle);
		overflow-y: auto;
	}

	.file-name {
		font: var(--type-label-md);
		color: var(--text-primary);
		overflow-wrap: anywhere;
	}

	.meta {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.meta dt {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.meta dd {
		font: var(--type-mono-sm);
		color: var(--text-secondary);
		overflow-wrap: anywhere;
	}

	.filmstrip {
		grid-area: strip;
		display: flex;
		gap: var(--space-1);
		padding: var(--space-3) var(--space-4) var(--space-4);
		overflow-x: auto;
		overscroll-behavior: contain;
		scrollbar-width: thin;
	}

	.thumb {
		position: relative;
		flex: 0 0 auto;
		width: 56px;
		height: 56px;
		padding: 0;
		overflow: hidden;
		border-radius: var(--radius-xs);
		background: var(--bg-raised);
		opacity: 0.5;
		outline-offset: -2px;
		transition: opacity var(--duration-micro) var(--ease-out-quint);
	}

	.thumb:hover {
		opacity: 0.85;
	}

	/* Centred while the strip fits, scrolling from its start once it does not. */
	.thumb:first-child {
		margin-left: auto;
	}

	.thumb:last-child {
		margin-right: auto;
	}

	.thumb[aria-current='true'] {
		opacity: 1;
		box-shadow: inset 0 0 0 2px var(--accent);
	}

	.thumb img,
	.thumb video {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
		pointer-events: none;
	}

	.thumb[aria-current='true'] img,
	.thumb[aria-current='true'] video {
		/* Inside the accent ring. */
		padding: 2px;
		border-radius: var(--radius-xs);
	}

	.thumb-badge {
		position: absolute;
		left: 3px;
		bottom: 3px;
		display: inline-flex;
		padding: 2px;
		border-radius: var(--radius-xs);
		background: rgba(0, 0, 0, 0.66);
		color: #fff;
	}

	@media (max-width: 899px) {
		.lightbox {
			grid-template:
				'top' auto
				'stage' minmax(0, 1fr)
				'details' auto
				'strip' auto
				/ minmax(0, 1fr);
		}

		.top-bar {
			grid-template-columns: minmax(0, 1fr) auto;
			padding: var(--space-2) var(--space-3);
		}

		.counter {
			display: none;
		}

		.stage {
			padding: var(--space-2) var(--space-3);
		}

		.step.prev {
			left: var(--space-1);
		}

		.step.next {
			right: var(--space-1);
		}

		.details {
			flex-direction: row;
			flex-wrap: wrap;
			align-items: baseline;
			gap: var(--space-1) var(--space-4);
			padding: var(--space-2) var(--space-3);
			border-left: none;
			border-top: 1px solid var(--border-subtle);
		}

		.meta {
			flex-direction: row;
			flex-wrap: wrap;
			gap: var(--space-1) var(--space-4);
		}

		.meta div {
			display: flex;
			gap: var(--space-1);
			align-items: baseline;
		}

		.filmstrip {
			padding: var(--space-2) var(--space-3) var(--space-3);
		}
	}

	/*
	 * The zoom. The media morphs between its tile and the stage over duration/medium; the
	 * dialog fades itself in (above), and fades out as it leaves. The page behind holds
	 * still while the Lightbox zooms, rather than cross-fading as it does between routes.
	 */
	:global(::view-transition-group(lightbox-media)) {
		/* Undo the shell's "no group animates" (global.css), for this group alone. */
		animation: revert;
		animation-duration: var(--duration-medium);
		animation-timing-function: var(--ease-out-quint);
	}

	:global(::view-transition-old(lightbox-media)),
	:global(::view-transition-new(lightbox-media)) {
		height: 100%;
		object-fit: cover;
		animation-duration: var(--duration-medium);
		animation-timing-function: var(--ease-out-quint);
	}

	:global(::view-transition-new(lightbox)) {
		animation: none;
	}

	:global(::view-transition-old(lightbox)) {
		animation-duration: var(--duration-medium);
		animation-timing-function: var(--ease-out-quint);
	}

	:global(:root.lightbox-zooming::view-transition-old(page)),
	:global(:root.lightbox-zooming::view-transition-new(page)) {
		animation: none;
	}
</style>
