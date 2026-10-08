<!--
	One message in Browse's feed, the proposal's MessageRow (audit #16). A header row
	shows the author's avatar, name and the time; a continuation (`continuation`), the
	same author's next message within the group's window (feed.ts), shows only its
	content, with its time in the gutter on hover. A reply shows who and what it answers
	above its header, linking there. On hover or keyboard focus a cluster of actions
	rises in the corner: copy a link to the message, open it in context. The row prints
	no ids.
-->
<script lang="ts">
	import { channelHref } from '#lib/routes.ts';
	import { withGuild } from '#lib/shell.svelte.ts';
	import type { Message, MessageReference } from '#lib/types.ts';
	import Avatar from './ui/Avatar.svelte';
	import Badge from './ui/Badge.svelte';
	import Icon from './ui/Icon.svelte';
	import IconButton from './ui/IconButton.svelte';

	let {
		message,
		continuation = false,
		highlighted = false,
		flash = false,
		tabindex = -1,
		onreference
	}: {
		message: Message;
		/** Whether the row continues the group of the header above it. */
		continuation?: boolean;
		/** Marks the message a link opened the reader on. */
		highlighted?: boolean;
		/** Briefly marks the message, as when a reply above was followed to it. */
		flash?: boolean;
		/**
		 * The row's place in the feed's roving focus: 0 for the one Tab reaches, whose
		 * actions Tab reaches next; -1 for the others, reached with J and K.
		 */
		tabindex?: 0 | -1;
		/**
		 * Following the reply's link to the message it answers. Call `preventDefault` on the
		 * event to handle it in place (the message is loaded); otherwise the link opens it.
		 */
		onreference?: (reference: MessageReference, event: MouseEvent) => void;
	} = $props();

	const authorName = $derived(
		message.author?.display_name || message.author?.username || 'Unknown author'
	);
	const href = $derived(channelHref(message.channel_id, { message: message.id }));
	const reference = $derived(message.reference ?? null);
	const referenceName = $derived(
		reference?.author?.display_name || reference?.author?.username || 'Unknown author'
	);

	const created = $derived(new Date(message.created_at));
	const time = $derived(created.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }));
	const shortTime = $derived(
		created.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: false })
	);
	const fullTime = $derived(formatFull(message.created_at));

	function formatFull(iso: string): string {
		return new Date(iso).toLocaleString('en-US', {
			weekday: 'long',
			month: 'long',
			day: 'numeric',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function isImageType(ct: string | null): boolean {
		return !!ct && ct.startsWith('image/');
	}

	interface Embed {
		title?: string;
		description?: string;
	}

	const embeds: Embed[] = $derived.by(() => {
		if (!message.embeds) return [];
		try {
			const parsed: unknown = JSON.parse(message.embeds);
			return Array.isArray(parsed) ? (parsed as Embed[]) : [];
		} catch {
			return [];
		}
	});

	let copied = $state(false);
	let copiedTimer: ReturnType<typeof setTimeout> | undefined;

	async function copyLink() {
		const url = new URL(withGuild(href), window.location.href).href;
		try {
			await navigator.clipboard.writeText(url);
			copied = true;
			clearTimeout(copiedTimer);
			copiedTimer = setTimeout(() => (copied = false), 1500);
		} catch {
			// No clipboard (an insecure origin, a denied permission): show the link to copy.
			window.prompt('Copy the link to this message', url);
		}
	}
</script>

<!-- An article in an ARIA feed (MessageFeed) is focusable: the feed's roving focus. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<article
	class="row"
	class:continuation
	class:pinned={message.pinned}
	class:highlighted
	class:flash
	data-message-id={message.id}
	aria-current={highlighted ? 'true' : undefined}
	aria-label="{authorName}, {fullTime}"
	{tabindex}
>
	{#if message.reference_id}
		<div class="reply">
			<span class="reply-spine" aria-hidden="true"></span>
			{#if reference}
				<a
					class="reply-link"
					href={channelHref(reference.channel_id, { message: reference.id })}
					onclick={(event) => onreference?.(reference, event)}
				>
					<Avatar src={reference.author?.avatar_url} name={referenceName} size={16} />
					<span class="sr-only">Replying to</span>
					<span class="reply-author">{referenceName}</span>
					<span class="reply-snippet truncate">
						{#if reference.snippet}{reference.snippet}{:else}<em>Attachment or embed</em>{/if}
					</span>
				</a>
			{:else}
				<span class="reply-missing">
					<Icon name="reply" size={14} /> Replying to a message that is not in the archive
				</span>
			{/if}
		</div>
	{/if}

	<div class="gutter">
		{#if continuation}
			<time class="gutter-time mono" datetime={message.created_at} title={fullTime}>{shortTime}</time>
		{:else}
			<Avatar src={message.author?.avatar_url} name={authorName} size={40} />
		{/if}
	</div>

	<div class="body">
		{#if !continuation}
			<div class="head">
				<span class="author">{authorName}</span>
				{#if message.author?.bot}
					<Badge tone="accent">BOT</Badge>
				{/if}
				<time class="time mono" datetime={message.created_at} title={fullTime}>{time}</time>
			</div>
		{/if}

		{#if message.content || message.pinned || message.edited_at}
			<p class="content">
				{message.clean_content || message.content}
				{#if message.edited_at}
					<span class="flag" title="Edited {formatFull(message.edited_at)}">(edited)</span>
				{/if}
				{#if message.pinned}
					<span class="flag pin" title="Pinned"><Icon name="pin" size={14} label="Pinned" /></span>
				{/if}
			</p>
		{/if}

		{#if message.attachments.length > 0}
			<div class="attachments">
				{#each message.attachments as att (att.id)}
					{#if isImageType(att.content_type)}
						<a href={att.url} target="_blank" rel="noopener noreferrer" class="attachment-img-link">
							<img
								class="attachment-img"
								src={att.proxy_url || att.url}
								alt={att.filename}
								loading="lazy"
							/>
						</a>
					{:else}
						<a href={att.url} target="_blank" rel="noopener noreferrer" class="attachment-file">
							<Icon name="paperclip" />
							<span class="file-name truncate">{att.filename}</span>
							<span class="file-size mono">{formatSize(att.size)}</span>
						</a>
					{/if}
				{/each}
			</div>
		{/if}

		{#if embeds.length > 0}
			<div class="embeds">
				{#each embeds as embed, i (i)}
					<div class="embed-card">
						{#if embed.title}
							<div class="embed-title">{embed.title}</div>
						{/if}
						{#if embed.description}
							<div class="embed-desc">{embed.description}</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}

		{#if message.reactions.length > 0}
			<div class="reactions">
				{#each message.reactions as react (react.id)}
					<span class="reaction">
						{#if react.emoji_name}
							<span class="reaction-emoji">{react.emoji_name}</span>
						{:else}
							<Icon name="circle-help" size={14} label="Unknown emoji" />
						{/if}
						<span class="reaction-count mono">{react.count}</span>
					</span>
				{/each}
			</div>
		{/if}
	</div>

	<div class="actions" role="toolbar" aria-label="Message actions">
		<IconButton
			icon={copied ? 'check' : 'link'}
			label={copied ? 'Link copied' : 'Copy link'}
			size="sm"
			{tabindex}
			onclick={copyLink}
		/>
		<a class="action-link" {href} aria-label="Open in context" title="Open in context" {tabindex}>
			<Icon name="arrow-up-right" size={14} />
		</a>
	</div>
</article>

<style>
	.row {
		position: relative;
		display: grid;
		grid-template-columns: 40px minmax(0, 1fr);
		column-gap: var(--space-3);
		padding: var(--space-1) var(--space-3);
		margin-top: var(--space-3);
		border: 1px solid transparent;
		border-radius: var(--radius-sm);
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.row.continuation {
		margin-top: 0;
	}

	.row:hover,
	.row:focus-within {
		background: var(--bg-hover);
	}

	.row:focus-visible {
		outline-offset: -2px;
	}

	.row.pinned {
		box-shadow: inset 2px 0 0 var(--accent);
	}

	/* The message a link opened the reader on. */
	.row.highlighted,
	.row.highlighted:hover {
		background: var(--accent-muted);
		border-color: var(--accent);
	}

	/* A message the reader just scrolled to from a reply. */
	.row.flash {
		animation: flash 1.6s var(--ease-out-quint);
	}

	@keyframes flash {
		from {
			background-color: var(--accent-glow);
		}
		to {
			background-color: transparent;
		}
	}

	/* ── Reply context ── */
	.reply {
		grid-column: 2;
		display: flex;
		align-items: center;
		min-width: 0;
		margin-bottom: 2px;
		position: relative;
	}

	/* A hook from the avatar column up to the line it answers. */
	.reply-spine {
		position: absolute;
		left: -32px;
		top: 50%;
		width: 26px;
		height: 10px;
		border-left: 2px solid var(--border-default);
		border-top: 2px solid var(--border-default);
		border-top-left-radius: var(--radius-sm);
	}

	.reply-link {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		min-width: 0;
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.reply-link:hover {
		color: var(--text-primary);
	}

	.reply-author {
		font: var(--type-label-sm);
		color: var(--text-primary);
		flex-shrink: 0;
	}

	.reply-snippet {
		min-width: 0;
	}

	.reply-missing {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-body-sm);
		font-style: italic;
		color: var(--text-tertiary);
	}

	/* ── Gutter and head ── */
	.gutter {
		grid-column: 1;
		padding-top: 2px;
	}

	.gutter-time {
		display: block;
		padding-top: 4px;
		text-align: right;
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		opacity: 0;
		transition: opacity var(--duration-micro) var(--ease-out-quint);
	}

	.row:hover .gutter-time,
	.row:focus-within .gutter-time {
		opacity: 1;
	}

	.body {
		grid-column: 2;
		min-width: 0;
	}

	.head {
		display: flex;
		align-items: baseline;
		gap: var(--space-2);
		min-width: 0;
	}

	.author {
		font: var(--type-heading-sm);
		color: var(--text-primary);
	}

	.time {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.content {
		font: var(--type-body-md);
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
	}

	.flag {
		font: var(--type-label-xs);
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	.flag.pin {
		display: inline-flex;
		vertical-align: -1px;
		color: var(--accent);
	}

	/* ── Attachments, embeds, reactions ── */
	.attachments {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-top: var(--space-2);
	}

	.attachment-img-link {
		display: block;
		border-radius: var(--radius-sm);
		overflow: hidden;
		border: 1px solid var(--border-subtle);
		max-width: min(400px, 100%);
	}

	.attachment-img {
		display: block;
		max-width: 100%;
		max-height: 300px;
		object-fit: contain;
		background: var(--bg-canvas);
	}

	.attachment-file {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		background: var(--bg-raised);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		font: var(--type-body-sm);
		color: var(--text-secondary);
		max-width: min(300px, 100%);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.attachment-file:hover {
		border-color: var(--border-default);
		color: var(--text-secondary);
	}

	.file-name {
		color: var(--text-primary);
	}

	.file-size {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.embeds {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		margin-top: var(--space-2);
	}

	.embed-card {
		border-left: 2px solid var(--accent-strong);
		padding: var(--space-2) var(--space-3);
		background: var(--bg-raised);
		border-radius: 0 var(--radius-xs) var(--radius-xs) 0;
	}

	.embed-title {
		font: var(--type-label-md);
		color: var(--accent);
		margin-bottom: var(--space-1);
	}

	.embed-desc {
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.reactions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
		margin-top: var(--space-2);
	}

	.reaction {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		height: 24px;
		padding: 0 var(--space-2);
		background: var(--bg-raised);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-full);
		font-size: 13px;
		color: var(--text-secondary);
	}

	.reaction-count {
		font: var(--type-mono-sm);
		color: var(--text-secondary);
	}

	/* ── Hover actions: rise 4px into place on hover or keyboard focus ── */
	.actions {
		position: absolute;
		top: -14px;
		right: var(--space-3);
		display: flex;
		align-items: center;
		gap: 2px;
		padding: 2px;
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		background: var(--bg-overlay);
		box-shadow: var(--shadow-floating);
		opacity: 0;
		transform: translateY(4px);
		pointer-events: none;
		transition:
			opacity var(--duration-micro) var(--ease-out-quint),
			transform var(--duration-micro) var(--ease-out-quint);
	}

	.row:hover .actions,
	.row:focus-within .actions {
		opacity: 1;
		transform: none;
		pointer-events: auto;
	}

	.action-link {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		border-radius: var(--radius-sm);
		color: var(--text-secondary);
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.action-link:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	@media (prefers-reduced-motion: reduce) {
		.actions {
			transform: none;
		}

		.row.flash {
			animation-duration: 0.01ms;
		}
	}
</style>
