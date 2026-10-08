<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { searchMessages, getGuild } from '#lib/api.ts';
	import { channelHref } from '#lib/routes.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { SearchResult, Channel } from '#lib/types.ts';
	import MessageCard from '#lib/components/MessageCard.svelte';
	import MessageSkeleton from '#lib/components/MessageSkeleton.svelte';
	import SearchBar from '#lib/components/SearchBar.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import Button from '#lib/components/ui/Button.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';

	let query = $state('');
	let results: SearchResult[] = $state([]);
	let totalResults = $state(0);
	let loading = $state(false);
	let searched = $state(false);
	let error = $state('');

	// Filters
	const guild = shell.guild;
	let channels: Channel[] = $state([]);
	let selectedChannel: string | null = $state(null);

	/** The query last searched for, which the URL's `q` carries. */
	let searchedFor: string | null = null;

	onMount(async () => {
		try {
			if (guild) channels = (await getGuild(guild.id)).channels;
		} catch (e) {
			console.error('Failed to load channels:', e);
		}
	});

	// The URL's `q` is the query: on arrival, and when the sidebar's search field sets it.
	$effect(() => {
		const urlQuery = page.url.searchParams.get('q');
		if (urlQuery && urlQuery !== searchedFor) {
			untrack(() => {
				query = urlQuery;
				void doSearch();
			});
		}
	});

	async function doSearch() {
		if (!query.trim()) return;
		searchedFor = query.trim();
		loading = true;
		searched = true;
		error = '';

		try {
			const res = await searchMessages(query.trim(), {
				guild_id: guild?.id,
				channel_id: selectedChannel ?? undefined,
				limit: 50,
			});
			results = res.results;
			totalResults = res.total;

			// Update URL
			const url = new URL(window.location.href);
			url.searchParams.set('q', query.trim());
			goto(url.pathname + url.search, { replace: true, reset: false });
		} catch (e) {
			error = e instanceof Error ? e.message : 'Search failed';
		} finally {
			loading = false;
		}
	}

	function handleSubmit(q: string) {
		query = q;
		doSearch();
	}

	function clearFilters() {
		selectedChannel = null;
		if (searched) doSearch();
	}
</script>

<div class="search-page">
	<header class="search-header">
		<div class="search-header-content">
			<h1 class="search-title">Search</h1>
			<p class="search-sub">
				Find messages in {guild?.name ?? 'the archive'}.
				<span class="search-note">AI semantic search coming soon.</span>
			</p>

			<div class="search-input-area">
				<SearchBar
					bind:value={query}
					placeholder="Search by keyword, username, or phrase..."
					label="Search messages"
					onsubmit={handleSubmit}
				/>
			</div>

			<!-- Filters -->
			<div class="filters">
				{#if channels.length > 0}
					<div class="filter-group">
						<label class="filter-label" for="search-channel">Channel</label>
						<select
							id="search-channel"
							class="filter-select"
							bind:value={selectedChannel}
							onchange={() => { if (searched) doSearch(); }}
						>
							<option value={null}>All channels</option>
							{#each channels as ch (ch.id)}
								<option value={ch.id}>#{ch.name}</option>
							{/each}
						</select>
					</div>
				{/if}

				{#if selectedChannel}
					<Button variant="ghost" size="sm" icon="x" onclick={clearFilters}>Clear filters</Button>
				{/if}

				{#if searched}
					<div class="result-count mono">
						{totalResults.toLocaleString()} result{totalResults !== 1 ? 's' : ''}
					</div>
				{/if}
			</div>
		</div>
	</header>

	<div class="search-results">
		<div class="results-column">
			{#if loading}
				<MessageSkeleton count={3} label="Searching…" />
			{:else if error}
				<Alert tone="danger" title="The search failed">{error}</Alert>
			{:else if searched && results.length === 0}
				<EmptyState
					icon="search-x"
					title={`No results found for “${query}”`}
					description="Try different keywords or remove filters."
				/>
			{:else if !searched}
				<EmptyState icon="search" title="Enter a search query above" />
			{:else}
				<div class="results-list">
					{#each results as result, i (result.message.id)}
						<div class="result-item enter" style:--i={i}>
							<div class="result-context">
								<a
									class="result-channel"
									href={channelHref(result.message.channel_id, { message: result.message.id })}
									title="Open in context"
								>
									<Badge icon="hash">{result.channel_name}</Badge>
								</a>
							</div>
							<MessageCard message={result.message} />
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.search-header {
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
		padding: var(--space-8) var(--space-6) var(--space-5);
	}

	.search-header-content {
		max-width: var(--size-reader-max);
		margin: 0 auto;
	}

	.search-title {
		font: var(--type-display-lg);
		letter-spacing: var(--tracking-display-lg);
		margin-bottom: var(--space-2);
	}

	.search-sub {
		font: var(--type-body-md);
		color: var(--text-secondary);
		margin-bottom: var(--space-5);
	}

	.search-note {
		color: var(--text-tertiary);
	}

	.search-input-area {
		max-width: 640px;
		margin-bottom: var(--space-4);
	}

	.filters {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		flex-wrap: wrap;
		min-height: 32px;
	}

	.filter-group {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.filter-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.filter-select {
		height: 28px;
		font: var(--type-label-sm);
		color: var(--text-primary);
		background: var(--bg-raised);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		padding: 0 var(--space-2);
		cursor: pointer;
	}

	.filter-select option {
		background: var(--bg-raised);
		color: var(--text-primary);
	}

	.result-count {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		margin-left: auto;
	}

	.search-results {
		padding: var(--space-6);
	}

	.results-column {
		max-width: var(--size-reader-max);
		margin: 0 auto;
	}

	.results-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.result-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.result-context {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	/* The channel badge opens the message in Browse. */
	.result-channel {
		display: inline-flex;
		border-radius: var(--radius-full);
		transition: opacity var(--duration-micro) var(--ease-out-quint);
	}

	.result-channel:hover {
		opacity: 0.8;
	}
</style>
