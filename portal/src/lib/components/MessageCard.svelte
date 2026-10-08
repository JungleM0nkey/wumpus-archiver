<script lang="ts">
	import type { Message } from '#lib/types.ts';
	import Badge from './ui/Badge.svelte';
	import Icon from './ui/Icon.svelte';

	let {
		message,
		highlighted = false
	}: {
		message: Message;
		/** Marks the message a link opened the reader on. */
		highlighted?: boolean;
	} = $props();

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

	function isImageType(ct: string | null): boolean {
		return !!ct && ct.startsWith('image/');
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

<article
	class="message-card"
	class:pinned={message.pinned}
	class:highlighted
	data-message-id={message.id}
	aria-current={highlighted ? 'true' : undefined}
>
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
					<Badge tone="accent">BOT</Badge>
				{/if}
			</div>
		</div>
		<div class="card-meta">
			{#if message.pinned}
				<span class="pin" title="Pinned"><Icon name="pin" size={14} label="Pinned" /></span>
			{/if}
			{#if message.edited_at}
				<Badge>edited</Badge>
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

	<div class="card-footer">
		<span class="msg-id mono">ID {message.id}</span>
		{#if message.reference_id}
			<Badge icon="reply">reply</Badge>
		{/if}
	</div>
</article>

<style>
	.message-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		padding: var(--space-4) var(--space-5);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.message-card:hover {
		border-color: var(--border-default);
	}

	.message-card.pinned {
		border-left: 2px solid var(--accent);
	}

	/* The message a link opened the reader on. */
	.message-card.highlighted,
	.message-card.highlighted:hover {
		background: var(--accent-muted);
		border-color: var(--accent);
	}

	.card-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		margin-bottom: var(--space-3);
	}

	.author-info {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		min-width: 0;
	}

	.avatar {
		width: 32px;
		height: 32px;
		border-radius: var(--radius-full);
		object-fit: cover;
		flex-shrink: 0;
	}

	.avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-secondary);
		font: var(--type-label-md);
		border: 1px solid var(--border-subtle);
	}

	.author-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
	}

	.author-name {
		font: var(--type-heading-sm);
		color: var(--text-primary);
	}

	.card-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex-shrink: 0;
	}

	.timestamp {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.pin {
		display: inline-flex;
		color: var(--accent);
	}

	.card-body {
		margin-bottom: var(--space-3);
	}

	.content {
		font: var(--type-body-md);
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
	}

	.attachments {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
	}

	.attachment-img-link {
		display: block;
		border-radius: var(--radius-sm);
		overflow: hidden;
		border: 1px solid var(--border-subtle);
		max-width: 400px;
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
		max-width: 300px;
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
		margin-bottom: var(--space-3);
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
		margin-bottom: var(--space-3);
	}

	.reaction-badge {
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

	.card-footer {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding-top: var(--space-2);
		border-top: 1px solid var(--border-subtle);
	}

	.msg-id {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}
</style>
