<script lang="ts">
	// The Media screen: a guild's attachments from the gallery timeline, in justified
	// rows under sticky month headers (MediaTimeline). Type, channel, author and sort are
	// filters in the URL (`type`, `channel`, `author`, `sort`), so a filtered view
	// survives a reload and can be linked to; changing one replaces the grid without
	// leaving the screen.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { getGuild } from '#lib/api.ts';
	import { guildHolding, shell, stickyHeader } from '#lib/shell.svelte.ts';
	import type { MediaType } from '#lib/media.ts';
	import type { Channel, GalleryAttachment } from '#lib/types.ts';
	import { ChannelType } from '#lib/types.ts';
	import MediaTimeline from '#lib/components/MediaTimeline.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Chip from '#lib/components/ui/Chip.svelte';

	const TYPES: { value: MediaType | null; label: string; noun: string }[] = [
		{ value: null, label: 'All', noun: 'media' },
		{ value: 'image', label: 'Images', noun: 'images' },
		{ value: 'video', label: 'Videos', noun: 'videos' },
		{ value: 'gif', label: 'GIFs', noun: 'GIFs' }
	];

	// ── The filters, read from the URL ──
	const params = $derived(page.url.searchParams);
	const type = $derived(TYPES.find((t) => t.value && t.value === params.get('type'))?.value ?? null);
	const channelId = $derived(params.get('channel') || null);
	const authorId = $derived(params.get('author') || null);
	const oldestFirst = $derived(params.get('sort') === 'oldest');

	let channels: Channel[] = $state([]);
	let ready = $state(false);
	/** Why the guild's channels could not be read, or ''. */
	let guildError = $state('');

	// Reported by the grid.
	let total = $state(0);
	let loading = $state(true);
	let error = $state('');
	let attachments: GalleryAttachment[] = $state([]);

	const selectedChannel = $derived(channels.find((c) => c.id === channelId));
	const authorName = $derived(attachments.find((a) => a.author_name)?.author_name ?? 'one author');

	onMount(async () => {
		const guild = shell.guild;
		if (!guild) {
			ready = true;
			return;
		}
		try {
			// A link naming a channel of another guild selects that guild first.
			const detail = channelId ? await guildHolding(channelId) : null;
			if (channelId && !detail) return;
			if (!channelId) ready = true;
			const { channels: all } = detail ?? (await getGuild(guild.id));
			channels = all.filter(
				(c) =>
					c.type === ChannelType.GUILD_TEXT ||
					c.type === ChannelType.GUILD_ANNOUNCEMENT ||
					c.id === channelId
			);
			ready = true;
		} catch (e) {
			guildError = e instanceof Error ? e.message : 'Failed to load the guild';
		}
	});

	/** Change one filter in the URL; the grid follows. */
	function setFilter(name: string, value: string | null) {
		// Build on a navigation still under way, so two quick changes both land.
		const from = pending ?? page.url.href;
		const url = new URL(from);
		if (value) url.searchParams.set(name, value);
		else url.searchParams.delete(name);
		if (url.href === from) return;
		const scroller = shell.scroller;
		if (scroller && scroller.scrollTop > 0) scroller.scrollTop = 0;
		const href = (pending = url.href);
		void goto(url.pathname + url.search, { reset: false }).finally(() => {
			if (pending === href) pending = null;
		});
	}

	/** The URL a filter change is navigating to, until it arrives. */
	let pending: string | null = null;

	let headerHeight = $state(0);

	const noun = $derived(TYPES.find((t) => t.value === type)?.noun ?? 'media');
	const emptyTitle = $derived(
		`No ${noun}${selectedChannel ? ` in #${selectedChannel.name}` : ''}${authorId ? ' from this author' : ''}.`
	);
</script>

<div class="media-page">
	<header class="media-header" use:stickyHeader bind:offsetHeight={headerHeight}>
		<div class="title-row">
			<h1>Media</h1>
			{#if !loading && !error && !guildError}
				<span class="total mono">{total.toLocaleString()} item{total !== 1 ? 's' : ''}</span>
			{/if}
		</div>
		<div class="toolbar">
			<div class="chips" role="group" aria-label="Type">
				{#each TYPES as t (t.label)}
					<Chip selected={type === t.value} onclick={() => setFilter('type', t.value)}>{t.label}</Chip>
				{/each}
			</div>
			<label class="field">
				<span class="field-label">Channel</span>
				<select
					class="select"
					value={channelId ?? ''}
					onchange={(e) => setFilter('channel', e.currentTarget.value || null)}
				>
					<option value="">All channels</option>
					{#each channels as ch (ch.id)}
						<option value={ch.id}>#{ch.name}</option>
					{/each}
				</select>
			</label>
			<label class="field">
				<span class="field-label">Sort</span>
				<select
					class="select"
					value={oldestFirst ? 'oldest' : 'newest'}
					onchange={(e) => setFilter('sort', e.currentTarget.value === 'oldest' ? 'oldest' : null)}
				>
					<option value="newest">Newest first</option>
					<option value="oldest">Oldest first</option>
				</select>
			</label>
			{#if authorId}
				<Chip selected icon="x" aria-label="Clear author filter" onclick={() => setFilter('author', null)}>
					From {authorName}
				</Chip>
			{/if}
		</div>
	</header>

	<div class="media-body">
		{#if guildError}
			<Alert tone="danger" title="Media could not be loaded">{guildError}</Alert>
		{:else}
			<MediaTimeline
				{channelId}
				{authorId}
				{type}
				{oldestFirst}
				{ready}
				stickyTop={headerHeight}
				{emptyTitle}
				bind:total
				bind:loading
				bind:error
				bind:loaded={attachments}
			/>
		{/if}
	</div>
</div>

<style>
	.media-page {
		min-height: 100%;
	}

	.media-header {
		position: sticky;
		top: 0;
		z-index: 3;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4) var(--space-6);
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
	}

	.title-row {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
	}

	.title-row h1 {
		font: var(--type-heading-lg);
	}

	.total {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.toolbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-4);
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
	}

	.field {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
	}

	.field-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.select {
		height: 28px;
		max-width: 220px;
		padding: 0 var(--space-2);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		background: var(--bg-raised);
		color: var(--text-primary);
		font: var(--type-label-sm);
		cursor: pointer;
	}

	.select option {
		background: var(--bg-raised);
		color: var(--text-primary);
	}

	.media-body {
		padding: 0 var(--space-6) var(--space-6);
	}

	@media (max-width: 767px) {
		.media-header {
			padding: var(--space-3) var(--space-4);
		}
		.media-body {
			padding: 0 var(--space-4) var(--space-4);
		}
	}
</style>
