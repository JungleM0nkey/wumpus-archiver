<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { searchMessages, getGuilds, getGuild } from '$lib/api';
	import type { SearchResult, Channel, Guild } from '$lib/types';
	import MessageCard from '$lib/components/MessageCard.svelte';
	import SearchBar from '$lib/components/SearchBar.svelte';

	let query = $state('');
	let results: SearchResult[] = $state([]);
	let totalResults = $state(0);
	let loading = $state(false);
	let searched = $state(false);
	let error = $state('');

	// Filters
	let guilds: Guild[] = $state([]);
	let channels: Channel[] = $state([]);
	let selectedGuild: string | null = $state(null);
	let selectedChannel: string | null = $state(null);

	// Load initial data
	onMount(async () => {
		try {
			guilds = await getGuilds();
			if (guilds.length > 0) {
				selectedGuild = guilds[0].id;
				const detail = await getGuild(guilds[0].id);
				channels = detail.channels;
			}
		} catch (e) {
			console.error('Failed to load guilds:', e);
		}

		// Check URL for initial query
		const urlQuery = page.url.searchParams.get('q');
		if (urlQuery) {
			query = urlQuery;
			await doSearch();
		}
	});

	async function doSearch() {
		if (!query.trim()) return;
		loading = true;
		searched = true;
		error = '';

		try {
			const res = await searchMessages(query.trim(), {
				guild_id: selectedGuild ?? undefined,
				channel_id: selectedChannel ?? undefined,
				limit: 50,
			});
			results = res.results;
			totalResults = res.total;

			// Update URL
			const url = new URL(window.location.href);
			url.searchParams.set('q', query.trim());
			goto(url.pathname + url.search, { replaceState: true, noScroll: true });
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
			<h1 class="search-title serif">Search<span class="dot">.</span></h1>
			<p class="search-sub">
				Find messages across the entire archive.
				<span class="mono" style="color: var(--text-faint);">AI semantic search coming soon.</span>
			</p>

			<div class="search-input-area">
				<SearchBar
					bind:value={query}
					placeholder="Search by keyword, username, or phrase..."
					onsubmit={handleSubmit}
				/>
			</div>

			<!-- Filters -->
			<div class="filters">
				{#if channels.length > 0}
					<div class="filter-group">
						<label class="filter-label mono">Channel</label>
						<select
							class="filter-select"
							bind:value={selectedChannel}
							onchange={() => { if (searched) doSearch(); }}
						>
							<option value={null}>All channels</option>
							{#each channels as ch}
								<option value={ch.id}>#{ch.name}</option>
							{/each}
						</select>
					</div>
				{/if}

				{#if selectedChannel}
					<button class="clear-filters-btn" onclick={clearFilters}>
						✕ Clear filters
					</button>
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
		{#if loading}
			<div class="center-state">
				<div class="spinner"></div>
				<span class="mono">Searching...</span>
			</div>
		{:else if error}
			<div class="center-state error">⚠ {error}</div>
		{:else if searched && results.length === 0}
			<div class="center-state">
				<div class="empty-icon">⌕</div>
				<span>No results found for "<strong>{query}</strong>"</span>
				<span class="mono" style="font-size: 13px; color: var(--text-muted);">
					Try different keywords or remove filters
				</span>
			</div>
		{:else if !searched}
			<div class="center-state">
				<div class="empty-icon">⌕</div>
				<span class="mono" style="color: var(--text-muted);">
					Enter a search query above
				</span>
			</div>
		{:else}
			<div class="results-list">
				{#each results as result, i (result.message.id)}
					<div class="result-item fade-in" style="animation-delay: {i * 30}ms">
						<div class="result-context">
							<span class="badge">#{result.channel_name}</span>
						</div>
						<MessageCard message={result.message} />
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.search-page {
		height: 100%;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.search-header {
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border);
		padding: var(--sp-8) var(--sp-6) var(--sp-5);
		flex-shrink: 0;
	}

	.search-header-content {
		max-width: var(--max-content);
		margin: 0 auto;
	}

	.search-title {
		font-size: 32px;
		font-weight: 700;
		letter-spacing: -0.03em;
		margin-bottom: var(--sp-2);
	}

	.dot { color: var(--accent); }

	.search-sub {
		font-size: 14px;
		color: var(--text-secondary);
		margin-bottom: var(--sp-5);
	}

	.search-input-area {
		max-width: 640px;
		margin-bottom: var(--sp-4);
	}

	.filters {
		display: flex;
		align-items: center;
		gap: var(--sp-4);
		flex-wrap: wrap;
	}

	.filter-group {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.filter-label {
		font-size: 11px;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.filter-select {
		font-family: var(--font-sans);
		font-size: 13px;
		color: var(--text-primary);
		background: var(--bg-raised);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: var(--sp-1) var(--sp-3);
		cursor: pointer;
	}

	.filter-select option {
		background: var(--bg-raised);
		color: var(--text-primary);
	}

	.clear-filters-btn {
		font-size: 12px;
		color: var(--text-muted);
		padding: var(--sp-1) var(--sp-2);
		border-radius: var(--radius-sm);
		transition: all 0.12s var(--ease-out);
	}

	.clear-filters-btn:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.result-count {
		font-size: 12px;
		color: var(--text-muted);
		margin-left: auto;
	}

	.search-results {
		flex: 1;
		overflow-y: auto;
		padding: var(--sp-6);
	}

	.results-list {
		max-width: var(--max-content);
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: var(--sp-4);
	}

	.result-item {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	.result-context {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.center-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-16) 0;
		color: var(--text-secondary);
		text-align: center;
	}

	.center-state.error { color: var(--error); }

	.empty-icon {
		font-size: 48px;
		color: var(--text-faint);
		margin-bottom: var(--sp-2);
	}

	.spinner {
		width: 20px; height: 20px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin { to { transform: rotate(360deg); } }
</style>
