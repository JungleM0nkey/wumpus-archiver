<script lang="ts">
	import { onMount } from 'svelte';
	import { getGuilds, getGuild, getStats } from '$lib/api';
	import type { Guild, Channel, Stats } from '$lib/types';

	let guild: Guild | null = $state(null);
	let channels: Channel[] = $state([]);
	let stats: Stats | null = $state(null);
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		try {
			const guilds = await getGuilds();
			if (guilds.length > 0) {
				const detail = await getGuild(guilds[0].id);
				guild = detail;
				channels = detail.channels;
				stats = await getStats(guilds[0].id);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load channels';
		} finally {
			loading = false;
		}
	});

	function formatDate(d: string | null): string {
		if (!d) return '—';
		return new Date(d).toLocaleDateString('en-US', {
			month: 'short', day: 'numeric', year: 'numeric'
		});
	}

	function sortedChannels(): Channel[] {
		return [...channels].sort((a, b) => {
			const countA = stats?.top_channels?.find(c => c.name === a.name)?.message_count ?? a.message_count;
			const countB = stats?.top_channels?.find(c => c.name === b.name)?.message_count ?? b.message_count;
			return countB - countA;
		});
	}

	function getMessageCount(ch: Channel): number {
		return stats?.top_channels?.find(c => c.name === ch.name)?.message_count ?? ch.message_count;
	}

	function getMaxCount(): number {
		if (!stats?.top_channels?.length) return 1;
		return Math.max(...stats.top_channels.map(c => c.message_count), 1);
	}
</script>

<div class="channels-page">
	<header class="page-header">
		<h1 class="serif">Channels<span class="dot">.</span></h1>
		<p class="header-sub">
			{#if guild}
				Browse all archived channels in <strong>{guild.name}</strong>
			{:else}
				Loading archive index...
			{/if}
		</p>
	</header>

	{#if loading}
		<div class="center-state">
			<div class="spinner"></div>
			<span class="mono">Loading channels...</span>
		</div>
	{:else if error}
		<div class="center-state error">⚠ {error}</div>
	{:else if channels.length === 0}
		<div class="center-state">No channels found in archive.</div>
	{:else}
		<div class="channels-grid">
			{#each sortedChannels() as ch (ch.id)}
				{@const count = getMessageCount(ch)}
				{@const pct = (count / getMaxCount()) * 100}
				<a class="channel-card" href="/channel/{ch.id}">
					<div class="channel-header">
						<span class="channel-hash">#</span>
						<span class="channel-name">{ch.name}</span>
						{#if ch.type === 'category'}
							<span class="badge">Category</span>
						{/if}
					</div>

					{#if ch.topic}
						<p class="channel-topic">{ch.topic}</p>
					{/if}

					<div class="channel-stats">
						<div class="stat-bar-bg">
							<div class="stat-bar-fill" style="width: {pct}%"></div>
						</div>
						<div class="stat-row">
							<span class="mono stat-count">
								{count.toLocaleString()} messages
							</span>
						{#if ch.last_scraped_at}
							<span class="mono stat-date">
								last scraped {formatDate(ch.last_scraped_at)}
								</span>
							{/if}
						</div>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.channels-page {
		padding: var(--sp-8) var(--sp-6);
		max-width: var(--max-content);
		margin: 0 auto;
	}

	.page-header {
		margin-bottom: var(--sp-8);
	}

	.page-header h1 {
		font-size: 32px;
		font-weight: 700;
		letter-spacing: -0.03em;
		margin-bottom: var(--sp-2);
	}

	.dot { color: var(--accent); }

	.header-sub {
		font-size: 14px;
		color: var(--text-secondary);
	}

	.channels-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
		gap: var(--sp-4);
	}

	.channel-card {
		display: block;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		padding: var(--sp-5);
		text-decoration: none;
		color: inherit;
		transition: all 0.15s var(--ease-out);
	}

	.channel-card:hover {
		border-color: var(--accent);
		transform: translateY(-2px);
		box-shadow: 0 4px 16px rgba(0,0,0,0.3);
	}

	.channel-header {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		margin-bottom: var(--sp-3);
	}

	.channel-hash {
		font-size: 22px;
		font-weight: 700;
		color: var(--text-faint);
	}

	.channel-name {
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.channel-topic {
		font-size: 13px;
		color: var(--text-muted);
		margin-bottom: var(--sp-4);
		line-height: 1.5;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.channel-stats {
		margin-top: auto;
	}

	.stat-bar-bg {
		height: 4px;
		background: var(--bg-hover);
		border-radius: 2px;
		overflow: hidden;
		margin-bottom: var(--sp-2);
	}

	.stat-bar-fill {
		height: 100%;
		background: var(--accent);
		border-radius: 2px;
		min-width: 2px;
		transition: width 0.3s var(--ease-out);
	}

	.stat-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.stat-count {
		font-size: 12px;
		color: var(--text-secondary);
	}

	.stat-date {
		font-size: 11px;
		color: var(--text-faint);
	}

	.center-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-16) 0;
		color: var(--text-secondary);
	}

	.center-state.error { color: var(--error); }

	.spinner {
		width: 20px; height: 20px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin { to { transform: rotate(360deg); } }
</style>
