<script lang="ts">
	// Browse: the channel pane beside the reader of the channel it has open. The pane
	// stays mounted from channel to channel, so the guild's channels are read once; the
	// page below it remounts for each channel and each message link.
	//
	// The pane is sticky in the shell's scroll container and scrolls its own list, so
	// the feed beside it scrolls the page. Below 768px Browse shows one at a time: the
	// pane at /browse, the reader at /browse/<channel>.
	import { onMount, tick } from 'svelte';
	import { page } from '$app/state';
	import { getGuild } from '#lib/api.ts';
	import { setBrowseGuild } from '#lib/browse.ts';
	import { channelGroups, channelIcon, filterGroups, isThread } from '#lib/channels.ts';
	import { channelHref } from '#lib/routes.ts';
	import { guildHolding, shell } from '#lib/shell.svelte.ts';
	import type { GuildDetail } from '#lib/types.ts';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import IconButton from '#lib/components/ui/IconButton.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	let { children } = $props();

	let detail = $state<GuildDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let query = $state('');
	let list: HTMLElement | undefined = $state();

	const selected = $derived(page.params.channel ?? null);
	const groups = $derived(channelGroups(detail?.channels ?? []));
	const shown = $derived(filterGroups(groups, query));
	const channelCount = $derived(groups.reduce((n, g) => n + g.channels.length, 0));
	// The reader remounts for another channel or another message link.
	const readerKey = $derived(`${selected}:${page.url.searchParams.get('message')}`);

	const checked = page.params.channel ?? null;
	let settle: (proceed: boolean) => void = () => {};
	const ready = new Promise<boolean>((resolve) => (settle = resolve));
	setBrowseGuild({
		get detail() {
			return detail;
		},
		ready,
		checked
	});

	onMount(async () => {
		try {
			// A channel link names a channel without its guild: read the guild that holds it.
			const read = checked
				? await guildHolding(checked)
				: shell.guild && (await getGuild(shell.guild.id));
			if (!read && checked && shell.guild) {
				settle(false);
				return;
			}
			detail = read || null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load channels';
		} finally {
			loading = false;
		}
		settle(true);
		await tick();
		revealSelected();
	});

	/** Scroll the pane's list, not the page, to the selected channel when it is out of view. */
	function revealSelected() {
		const row = list?.querySelector<HTMLElement>('[aria-current="page"]');
		if (!list || !row) return;
		const top = row.offsetTop - list.offsetTop;
		if (top < list.scrollTop || top + row.offsetHeight > list.scrollTop + list.clientHeight) {
			list.scrollTop = top - (list.clientHeight - row.offsetHeight) / 2;
		}
	}
</script>

<div class="browse" class:reading={selected !== null}>
	<aside class="channel-pane" aria-label="Channels">
		<div class="pane-head">
			<div class="pane-title-row">
				<h2 class="pane-title">Channels</h2>
				{#if !loading && !error}
					<Badge mono>{channelCount}</Badge>
				{/if}
			</div>
			<div class="filter">
				<Icon name="search" size={14} />
				<input
					class="filter-input"
					type="search"
					bind:value={query}
					placeholder="Filter channels"
					aria-label="Filter channels"
				/>
				{#if query}
					<IconButton icon="x" label="Clear filter" size="sm" onclick={() => (query = '')} />
				{/if}
			</div>
		</div>

		<div class="channel-list" bind:this={list}>
			{#if loading}
				<div class="list-skeleton" aria-busy="true">
					<span class="sr-only" role="status">Loading channels…</span>
					{#each [0, 1, 2, 3, 4] as i (i)}
						<Skeleton height="16px" width={`${70 - i * 8}%`} />
					{/each}
				</div>
			{:else if error}
				<Alert tone="danger" title="Channels could not be loaded">{error}</Alert>
			{:else if shown.length === 0}
				<EmptyState
					compact
					icon={query ? 'search-x' : 'inbox'}
					title={query ? `No channels match “${query.trim()}”` : 'No channels archived'}
				/>
			{:else}
				{#each shown as group (group.category?.id ?? '')}
					<section class="channel-group">
						{#if group.category}
							<h3 class="category truncate">{group.category.name}</h3>
						{/if}
						<ul>
							{#each group.channels as channel (channel.id)}
								<li>
									<a
										href={channelHref(channel.id)}
										class="channel-item"
										class:thread={isThread(channel)}
										aria-current={channel.id === selected ? 'page' : undefined}
									>
										<Icon name={channelIcon(channel.type)} />
										<span class="channel-name truncate">{channel.name}</span>
										<span class="channel-count mono" title="Messages archived">
											{channel.message_count.toLocaleString()}
										</span>
									</a>
								</li>
							{/each}
						</ul>
					</section>
				{/each}
			{/if}
		</div>
	</aside>

	<div class="browse-main">
		{#key readerKey}
			{@render children()}
		{/key}
	</div>
</div>

<style>
	/* At least the shell's height, so the feed can sit at its bottom. */
	.browse {
		display: flex;
		align-items: flex-start;
		min-height: 100%;
	}

	/* The pane stays in view, filling the shell's height, and scrolls its own list. */
	.channel-pane {
		position: sticky;
		top: 0;
		height: var(--shell-viewport-height);
		width: var(--size-sidebar);
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		background: var(--bg-surface);
		border-right: 1px solid var(--border-subtle);
	}

	.pane-head {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
	}

	.pane-title-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.pane-title {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-secondary);
	}

	.filter {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		height: 32px;
		padding: 0 var(--space-1) 0 var(--space-2);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		background: var(--bg-canvas);
		color: var(--text-tertiary);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.filter:focus-within {
		border-color: var(--border-strong);
	}

	.filter-input {
		flex: 1;
		min-width: 0;
		height: 100%;
		font: var(--type-body-sm);
		color: var(--text-primary);
		outline: none;
	}

	.filter-input::placeholder {
		color: var(--text-tertiary);
	}

	/* Hide the browser's own clear button; the pane has its own. */
	.filter-input::-webkit-search-cancel-button {
		display: none;
	}

	.channel-list {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: var(--space-2);
	}

	.list-skeleton {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-2);
	}

	.channel-group + .channel-group {
		margin-top: var(--space-3);
	}

	.category {
		padding: var(--space-2) var(--space-2) var(--space-1);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	ul {
		list-style: none;
	}

	.channel-item {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		height: 32px;
		padding: 0 var(--space-2);
		border-radius: var(--radius-sm);
		font: var(--type-label-md);
		color: var(--text-secondary);
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.channel-item.thread {
		padding-left: var(--space-6);
	}

	.channel-item :global(.icon) {
		color: var(--text-tertiary);
	}

	.channel-item:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.channel-item[aria-current='page'] {
		background: var(--bg-active);
		color: var(--text-primary);
	}

	.channel-item[aria-current='page'] :global(.icon) {
		color: var(--accent);
	}

	.channel-name {
		flex: 1;
		min-width: 0;
	}

	.channel-count {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		flex-shrink: 0;
	}

	.browse-main {
		flex: 1;
		align-self: stretch;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	/* One pane at a time: the channel list at /browse, the reader at /browse/<channel>. */
	@media (max-width: 767px) {
		.browse.reading .channel-pane {
			display: none;
		}

		.browse:not(.reading) .channel-pane {
			position: static;
			align-self: stretch;
			width: 100%;
			height: auto;
			border-right: none;
		}

		.browse:not(.reading) .channel-list {
			overflow-y: visible;
		}

		.browse:not(.reading) .browse-main {
			display: none;
		}
	}
</style>
