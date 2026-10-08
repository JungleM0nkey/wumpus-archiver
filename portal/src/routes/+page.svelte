<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { getGuilds, getStats } from '#lib/api.ts';
	import type { Guild, Stats } from '#lib/types.ts';
	import StatCard from '#lib/components/StatCard.svelte';
	import SearchBar from '#lib/components/SearchBar.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	let guilds: Guild[] = $state([]);
	let stats: Stats | null = $state(null);
	let loading = $state(true);
	let error = $state('');
	let searchQuery = $state('');

	onMount(async () => {
		try {
			guilds = await getGuilds();
			if (guilds.length > 0) {
				stats = await getStats(guilds[0].id);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load data';
		} finally {
			loading = false;
		}
	});

	function handleSearch(query: string) {
		goto(`/search?q=${encodeURIComponent(query)}`);
	}

	function formatDate(iso: string | null): string {
		if (!iso) return 'Never';
		return new Date(iso).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		});
	}
</script>

<div class="dashboard">
	<header class="hero">
		<h1 class="hero-title">Archive</h1>
		<p class="hero-sub">Browse, search, and explore your Discord server history.</p>
		<div class="hero-search">
			<SearchBar
				bind:value={searchQuery}
				placeholder="Search messages, users, channels..."
				label="Search the archive"
				onsubmit={handleSearch}
			/>
		</div>
	</header>

	{#if loading}
		<div class="loading" aria-busy="true">
			<span class="sr-only" role="status">Loading archive data…</span>
			<div class="stats-grid">
				{#each [0, 1, 2, 3] as i (i)}
					<div class="tile-skeleton">
						<Skeleton width="72px" height="10px" />
						<Skeleton width="96px" height="28px" />
					</div>
				{/each}
			</div>
			<div class="rows-skeleton">
				{#each [0, 1, 2, 3, 4] as i (i)}
					<Skeleton height="20px" />
				{/each}
			</div>
		</div>
	{:else if error}
		<Alert tone="danger" title="The archive could not be loaded">
			<p>{error}</p>
			<p>Make sure the API server is running: <code>wumpus-archiver serve archive.db</code></p>
		</Alert>
	{:else if guilds.length === 0}
		<EmptyState
			icon="archive"
			title="Nothing archived yet"
			description="Scrape a guild from the Archive screen and it will show up here."
		/>
	{:else}
		{#if stats}
			<section class="section">
				<h2 class="section-title">
					<Icon name="dashboard" />
					Overview
					{#if guilds[0]}
						<Badge tone="accent">{guilds[0].name}</Badge>
					{/if}
				</h2>
				<div class="stats-grid">
					<StatCard label="Messages" value={stats.total_messages} icon="message" index={0} />
					<StatCard label="Channels" value={stats.total_channels} icon="hash" index={1} />
					<StatCard label="Users" value={stats.total_users} icon="users" index={2} />
					<StatCard label="Attachments" value={stats.total_attachments} icon="paperclip" index={3} />
				</div>
			</section>
		{/if}

		{#if stats && stats.top_channels.length > 0}
			<section class="section">
				<h2 class="section-title">
					<Icon name="chart" />
					Most Active Channels
				</h2>
				<div class="bar-chart">
					{#each stats.top_channels as ch, i (ch.id)}
						{@const maxCount = stats!.top_channels[0].message_count}
						<a href="/channel/{ch.id}" class="bar-row enter" style:--i={i}>
							<span class="bar-label truncate">#{ch.name}</span>
							<div class="bar-track">
								<div
									class="bar-fill"
									style="width: {(Number(ch.message_count) / Number(maxCount)) * 100}%"
								></div>
							</div>
							<span class="bar-value mono">{Number(ch.message_count).toLocaleString()}</span>
						</a>
					{/each}
				</div>
			</section>
		{/if}

		{#if stats && stats.top_users.length > 0}
			<section class="section">
				<h2 class="section-title">
					<Icon name="users" />
					Top Contributors
				</h2>
				<div class="contributors-grid">
					{#each stats.top_users as user, i (user.id)}
						<a href="/users/{user.id}" class="contributor-card enter" style:--i={i}>
							<span class="contributor-rank mono">#{i + 1}</span>
							{#if user.avatar_url}
								<img class="contributor-avatar" src={user.avatar_url} alt={user.display_name} />
							{:else}
								<div class="contributor-avatar avatar-fallback">
									{(user.username || '?')[0].toUpperCase()}
								</div>
							{/if}
							<div class="contributor-info">
								<span class="contributor-name">{user.display_name}</span>
								<span class="contributor-handle mono">@{user.username}</span>
							</div>
							<span class="contributor-count mono">{Number(user.message_count).toLocaleString()}</span>
						</a>
					{/each}
				</div>
			</section>
		{/if}

		{#if guilds[0]}
			<section class="section">
				<h2 class="section-title">
					<Icon name="archive" />
					Archive Info
				</h2>
				<div class="meta-grid">
					<div class="meta-item">
						<span class="meta-label">First Scraped</span>
						<span class="meta-value mono">{formatDate(guilds[0].first_scraped_at)}</span>
					</div>
					<div class="meta-item">
						<span class="meta-label">Last Updated</span>
						<span class="meta-value mono">{formatDate(guilds[0].last_scraped_at)}</span>
					</div>
					<div class="meta-item">
						<span class="meta-label">Scrape Count</span>
						<span class="meta-value mono">{guilds[0].scrape_count}</span>
					</div>
					<div class="meta-item">
						<span class="meta-label">Members (at scrape)</span>
						<span class="meta-value mono">{guilds[0].member_count?.toLocaleString() || '—'}</span>
					</div>
				</div>
			</section>
		{/if}
	{/if}
</div>

<style>
	.dashboard {
		max-width: var(--size-reader-max);
		margin: 0 auto;
		padding: var(--space-10) var(--space-6);
	}

	.hero {
		max-width: 640px;
		margin-bottom: var(--space-10);
	}

	.hero-title {
		font: var(--type-display-xl);
		letter-spacing: var(--tracking-display-xl);
		color: var(--text-primary);
		margin-bottom: var(--space-2);
	}

	.hero-sub {
		font: var(--type-body-md);
		color: var(--text-secondary);
		margin-bottom: var(--space-6);
	}

	.hero-search {
		max-width: 560px;
	}

	.section {
		margin-bottom: var(--space-10);
	}

	.section-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-heading-md);
		color: var(--text-primary);
		margin-bottom: var(--space-4);
	}

	.section-title :global(.icon) {
		color: var(--text-secondary);
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: var(--space-3);
	}

	.loading {
		display: flex;
		flex-direction: column;
		gap: var(--space-10);
	}

	.tile-skeleton {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4) var(--space-5);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		background: var(--bg-surface);
	}

	.rows-skeleton {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.bar-chart {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.bar-row {
		display: grid;
		grid-template-columns: 160px 1fr 80px;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-sm);
		color: inherit;
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.bar-row:hover {
		background: var(--bg-hover);
		color: inherit;
	}

	.bar-label {
		font: var(--type-body-md);
		color: var(--text-secondary);
	}

	.bar-track {
		height: 6px;
		background: var(--bg-raised);
		border-radius: var(--radius-full);
		overflow: hidden;
	}

	.bar-fill {
		height: 100%;
		background: var(--accent);
		border-radius: var(--radius-full);
	}

	.bar-value {
		font: var(--type-mono-md);
		color: var(--text-secondary);
		text-align: right;
	}

	.contributors-grid {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.contributor-card {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-sm);
		color: inherit;
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.contributor-card:hover {
		background: var(--bg-hover);
		color: inherit;
	}

	.contributor-rank {
		width: 28px;
		font: var(--type-mono-md);
		color: var(--text-tertiary);
		text-align: center;
	}

	.contributor-avatar {
		width: 32px;
		height: 32px;
		border-radius: var(--radius-full);
		object-fit: cover;
		flex-shrink: 0;
	}

	.contributor-avatar.avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-secondary);
		font: var(--type-label-md);
	}

	.contributor-info {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.contributor-name {
		font: var(--type-label-md);
		color: var(--text-primary);
	}

	.contributor-handle {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.contributor-count {
		font: var(--type-mono-md);
		color: var(--text-secondary);
	}

	.meta-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
		gap: var(--space-3);
	}

	.meta-item {
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.meta-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.meta-value {
		font: var(--type-mono-md);
		color: var(--text-primary);
	}

	@media (max-width: 700px) {
		.stats-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.bar-row {
			grid-template-columns: 110px 1fr 56px;
		}
	}
</style>
