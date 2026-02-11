<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { getGuilds, getStats } from '$lib/api';
	import type { Guild, Stats } from '$lib/types';
	import StatCard from '$lib/components/StatCard.svelte';
	import SearchBar from '$lib/components/SearchBar.svelte';

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
		<div class="hero-content">
			<h1 class="hero-title serif">
				Archive<span class="hero-dot">.</span>
			</h1>
			<p class="hero-sub">Browse, search, and explore your Discord server history.</p>
			<div class="hero-search">
				<SearchBar
					bind:value={searchQuery}
					placeholder="Search messages, users, channels..."
					onsubmit={handleSearch}
				/>
			</div>
		</div>
	</header>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<span class="mono">Loading archive data...</span>
		</div>
	{:else if error}
		<div class="error-state">
			<p>⚠ {error}</p>
			<p class="mono" style="font-size: 13px; color: var(--text-muted);">
				Make sure the API server is running: wumpus-archiver serve archive.db
			</p>
		</div>
	{:else}
		{#if stats}
			<section class="section fade-in">
				<h2 class="section-title">
					<span class="section-icon">◈</span>
					Overview
					{#if guilds[0]}
						<span class="badge accent">{guilds[0].name}</span>
					{/if}
				</h2>
				<div class="stats-grid">
					<StatCard label="Messages" value={stats.total_messages} icon="✉" />
					<StatCard label="Channels" value={stats.total_channels} icon="≡" />
					<StatCard label="Users" value={stats.total_users} icon="◉" />
					<StatCard label="Attachments" value={stats.total_attachments} icon="📎" />
				</div>
			</section>
		{/if}

		{#if stats && stats.top_channels.length > 0}
			<section class="section fade-in" style="animation-delay: 100ms">
				<h2 class="section-title">
					<span class="section-icon">▤</span>
					Most Active Channels
				</h2>
				<div class="bar-chart">
					{#each stats.top_channels as ch, i}
						{@const maxCount = stats!.top_channels[0].message_count}
						<a href="/channels" class="bar-row" style="animation-delay: {i * 40}ms">
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
			<section class="section fade-in" style="animation-delay: 200ms">
				<h2 class="section-title">
					<span class="section-icon">◉</span>
					Top Contributors
				</h2>
				<div class="contributors-grid">
					{#each stats.top_users as user, i}
						<a href="/users/{user.id}" class="contributor-card">
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
			<section class="section fade-in" style="animation-delay: 300ms">
				<h2 class="section-title">
					<span class="section-icon">⟐</span>
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
		max-width: var(--max-content);
		margin: 0 auto;
		padding: var(--sp-8) var(--sp-6);
	}

	.hero { margin-bottom: var(--sp-10); }

	.hero-content { max-width: 640px; }

	.hero-title {
		font-size: 48px;
		font-weight: 700;
		letter-spacing: -0.04em;
		line-height: 1;
		margin-bottom: var(--sp-3);
		color: var(--text-primary);
	}

	.hero-dot { color: var(--accent); }

	.hero-sub {
		font-size: 16px;
		color: var(--text-secondary);
		margin-bottom: var(--sp-6);
		line-height: 1.5;
	}

	.hero-search { max-width: 560px; }

	.section { margin-bottom: var(--sp-10); }

	.section-title {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: var(--sp-5);
	}

	.section-icon { color: var(--accent); font-size: 14px; }

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: var(--sp-4);
	}

	.bar-chart {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	.bar-row {
		display: grid;
		grid-template-columns: 160px 1fr 80px;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-2) var(--sp-3);
		border-radius: var(--radius-md);
		transition: background 0.15s var(--ease-out);
		animation: fadeIn 0.3s var(--ease-out) both;
		text-decoration: none;
		color: inherit;
	}

	.bar-row:hover { background: var(--bg-hover); text-decoration: none; }

	.bar-label { font-size: 14px; color: var(--text-secondary); }

	.bar-track {
		height: 8px;
		background: var(--bg-raised);
		border-radius: 4px;
		overflow: hidden;
	}

	.bar-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--accent-dim), var(--accent));
		border-radius: 4px;
		transition: width 0.5s var(--ease-out);
	}

	.bar-value { font-size: 13px; color: var(--text-muted); text-align: right; }

	.contributors-grid {
		display: flex;
		flex-direction: column;
		gap: var(--sp-1);
	}

	.contributor-card {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-3) var(--sp-4);
		border-radius: var(--radius-md);
		transition: background 0.15s var(--ease-out);
		text-decoration: none;
		color: inherit;
	}

	.contributor-card:hover { background: var(--bg-hover); text-decoration: none; }

	.contributor-rank { font-size: 13px; color: var(--text-faint); width: 28px; text-align: center; }

	.contributor-avatar {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		object-fit: cover;
		flex-shrink: 0;
	}

	.contributor-avatar.avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-muted);
		font-weight: 600;
		font-size: 13px;
	}

	.contributor-info { flex: 1; display: flex; flex-direction: column; }

	.contributor-name { font-size: 14px; font-weight: 500; color: var(--text-primary); }

	.contributor-handle { font-size: 12px; color: var(--text-muted); }

	.contributor-count { font-size: 13px; color: var(--text-secondary); }

	.meta-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: var(--sp-3);
	}

	.meta-item {
		padding: var(--sp-4);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		display: flex;
		flex-direction: column;
		gap: var(--sp-1);
	}

	.meta-label {
		font-size: 12px; color: var(--text-muted);
		text-transform: uppercase; letter-spacing: 0.05em;
	}

	.meta-value { font-size: 14px; color: var(--text-primary); }

	.loading-state {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		justify-content: center;
		padding: var(--sp-16) 0;
		color: var(--text-muted);
	}

	.spinner {
		width: 20px; height: 20px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin { to { transform: rotate(360deg); } }

	.error-state {
		text-align: center;
		padding: var(--sp-16) 0;
		color: var(--error);
	}
</style>
