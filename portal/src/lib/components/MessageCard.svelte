<script lang="ts">
	import type { Attachment, GalleryAttachment, Message } from '$lib/types';
	import Lightbox from './Lightbox.svelte';

	let { message }: { message: Message } = $props();

	const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.bmp', '.tiff']);

	function formatTime(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		});
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function isImage(att: Attachment): boolean {
		if (att.content_type?.startsWith('image/')) return true;
		const ext = att.filename.includes('.') ? '.' + att.filename.split('.').pop()!.toLowerCase() : '';
		return IMAGE_EXTENSIONS.has(ext);
	}

	function toGalleryAttachment(att: Attachment): GalleryAttachment {
		return {
			...att,
			created_at: message.created_at,
			author_name: message.author?.display_name || message.author?.username || null,
			author_avatar_url: message.author?.avatar_url || null,
			channel_id: message.channel_id,
			channel_name: null,
		};
	}

	let imageAttachments = $derived(message.attachments.filter(isImage));
	let lightboxIndex: number | null = $state(null);

	function openLightbox(att: Attachment) {
		lightboxIndex = imageAttachments.indexOf(att);
	}

	let parsedEmbeds: object[] = $derived.by(() => {
		if (!message.embeds) return [];
		try {
			return JSON.parse(message.embeds);
		} catch {
			return [];
		}
	});
</script>

<article class="message-card" class:pinned={message.pinned}>
	<div class="card-header">
		<div class="author-info">
			{#if message.author?.avatar_url}
				<img
					class="avatar"
					src={message.author.avatar_url}
					alt={message.author.display_name || message.author.username}
				/>
			{:else}
				<div class="avatar avatar-fallback">
					{(message.author?.username || '?')[0].toUpperCase()}
				</div>
			{/if}
			<div class="author-meta">
				<span class="author-name">
					{message.author?.display_name || message.author?.username || 'Unknown'}
				</span>
				{#if message.author?.bot}
					<span class="badge accent">BOT</span>
				{/if}
			</div>
		</div>
		<div class="card-meta">
			{#if message.pinned}
				<span class="pin-icon" title="Pinned">📌</span>
			{/if}
			{#if message.edited_at}
				<span class="badge">edited</span>
			{/if}
			<time class="timestamp mono" datetime={message.created_at}>
				{formatTime(message.created_at)}
			</time>
		</div>
	</div>

	{#if message.content}
		<div class="card-body">
			<p class="content">{message.clean_content || message.content}</p>
		</div>
	{/if}

	{#if message.attachments.length > 0}
		<div class="attachments">
			{#each message.attachments as att}
				{#if isImage(att)}
					<button class="attachment-img-link" onclick={() => openLightbox(att)}>
						<img
							class="attachment-img"
							src={att.url}
							alt={att.filename}
							loading="lazy"
						/>
					</button>
				{:else}
					<a href={att.url} target="_blank" rel="noopener" class="attachment-file">
						<span class="file-icon">📎</span>
						<span class="file-name truncate">{att.filename}</span>
						<span class="file-size mono">{formatSize(att.size)}</span>
					</a>
				{/if}
			{/each}
		</div>
	{/if}

	{#if lightboxIndex !== null}
		<Lightbox
			attachment={toGalleryAttachment(imageAttachments[lightboxIndex])}
			onclose={() => lightboxIndex = null}
			onnext={() => { if (lightboxIndex !== null && lightboxIndex < imageAttachments.length - 1) lightboxIndex++; }}
			onprev={() => { if (lightboxIndex !== null && lightboxIndex > 0) lightboxIndex--; }}
			hasPrev={lightboxIndex > 0}
			hasNext={lightboxIndex < imageAttachments.length - 1}
		/>
	{/if}

	{#if parsedEmbeds.length > 0}
		<div class="embeds">
			{#each parsedEmbeds as embed}
				<div class="embed-card">
					{#if (embed as any).title}
						<div class="embed-title">{(embed as any).title}</div>
					{/if}
					{#if (embed as any).description}
						<div class="embed-desc">{(embed as any).description}</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	{#if message.reactions.length > 0}
		<div class="reactions">
			{#each message.reactions as react}
				<span class="reaction-badge">
					<span class="reaction-emoji">{react.emoji_name || '❓'}</span>
					<span class="reaction-count mono">{react.count}</span>
				</span>
			{/each}
		</div>
	{/if}

	<div class="card-footer">
		<span class="msg-id mono">ID {message.id}</span>
		{#if message.reference_id}
			<span class="badge">↩ reply</span>
		{/if}
	</div>
</article>

<style>
	.message-card {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		padding: var(--sp-5);
		transition: border-color 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
	}

	.message-card:hover {
		border-color: var(--border-strong);
		box-shadow: var(--shadow-sm);
	}

	.message-card.pinned {
		border-left: 3px solid var(--accent);
	}

	.card-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--sp-3);
		margin-bottom: var(--sp-3);
	}

	.author-info {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
	}

	.avatar {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		object-fit: cover;
		flex-shrink: 0;
	}

	.avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-secondary);
		font-weight: 600;
		font-size: 14px;
		border: 1px solid var(--border);
	}

	.author-meta {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.author-name {
		font-weight: 600;
		font-size: 14px;
		color: var(--text-primary);
	}

	.card-meta {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		flex-shrink: 0;
	}

	.timestamp {
		font-size: 12px;
		color: var(--text-muted);
	}

	.pin-icon {
		font-size: 12px;
	}

	.card-body {
		margin-bottom: var(--sp-3);
	}

	.content {
		font-size: 14px;
		line-height: 1.65;
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
	}

	.attachments {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-2);
		margin-bottom: var(--sp-3);
	}

	.attachment-img-link {
		display: block;
		border-radius: var(--radius-md);
		overflow: hidden;
		border: 1px solid var(--border);
		max-width: 400px;
		padding: 0;
		background: none;
		cursor: pointer;
		transition: border-color 0.15s var(--ease-out);
	}

	.attachment-img-link:hover {
		border-color: var(--accent);
	}

	.attachment-img {
		display: block;
		max-width: 100%;
		max-height: 300px;
		object-fit: contain;
		background: var(--bg-base);
	}

	.attachment-file {
		display: inline-flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-2) var(--sp-3);
		background: var(--bg-raised);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		font-size: 13px;
		color: var(--text-secondary);
		text-decoration: none;
		max-width: 300px;
		transition: border-color 0.15s var(--ease-out);
	}

	.attachment-file:hover {
		border-color: var(--border-strong);
		text-decoration: none;
	}

	.file-name { color: var(--text-primary); }
	.file-size { font-size: 11px; color: var(--text-muted); }

	.embeds {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
		margin-bottom: var(--sp-3);
	}

	.embed-card {
		border-left: 3px solid var(--accent-dim);
		padding: var(--sp-2) var(--sp-3);
		background: var(--bg-raised);
		border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
	}

	.embed-title {
		font-weight: 600;
		font-size: 13px;
		color: var(--accent-text);
		margin-bottom: var(--sp-1);
	}

	.embed-desc {
		font-size: 13px;
		color: var(--text-secondary);
		line-height: 1.5;
	}

	.reactions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-1);
		margin-bottom: var(--sp-3);
	}

	.reaction-badge {
		display: inline-flex;
		align-items: center;
		gap: var(--sp-1);
		padding: 2px 8px;
		background: var(--bg-raised);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		font-size: 13px;
	}

	.reaction-count {
		font-size: 11px;
		color: var(--text-muted);
	}

	.card-footer {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding-top: var(--sp-2);
		border-top: 1px solid var(--border);
	}

	.msg-id {
		font-size: 11px;
		color: var(--text-faint);
	}
</style>
