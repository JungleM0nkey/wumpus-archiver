<script lang="ts">
	import { onMount } from 'svelte';
	import { getGuild, getStats } from '#lib/api.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import { ChannelType, type Guild, type Channel, type Stats } from '#lib/types.ts';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	let guild: Guild | null = $state(null);
	let channels: Channel[] = $state([]);
	let stats: Stats | null = $state(null);
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		const selected = shell.guild;
		try {
			if (selected) {
				const detail = await getGuild(selected.id);
				guild = detail;
				channels = detail.channels;
				stats = await getStats(selected.id);
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
		<h1>Channels</h1>
		<p class="header-sub">
			{#if guild}
				Browse all archived channels in <strong>{guild.name}</strong>, or
				<a href="/timeline">read them as a timeline</a>.
			{:else}
				Loading archive index...
			{/if}
		</p>
	</header>

	{#if loading}
		<div class="channels-grid" aria-busy="true">
			<span class="sr-only" role="status">Loading channels…</span>
			{#each [0, 1, 2, 3] as i (i)}
				<div class="channel-card skeleton-card">
					<Skeleton width="45%" height="16px" />
					<Skeleton width="80%" height="12px" />
					<Skeleton height="4px" radius="full" />
				</div>
			{/each}
		</div>
	{:else if error}
		<Alert tone="danger" title="The channels could not be loaded">{error}</Alert>
	{:else if channels.length === 0}
		<EmptyState icon="hash" title="No channels found in archive." />
	{:else}
		<div class="channels-grid">
			{#each sortedChannels() as ch, i (ch.id)}
				{@const count = getMessageCount(ch)}
				{@const pct = (count / getMaxCount()) * 100}
				<a class="channel-card enter" style:--i={i} href="/channel/{ch.id}">
					<div class="channel-header">
						<Icon name="hash" size={18} />
						<span class="channel-name">{ch.name}</span>
						{#if ch.type === ChannelType.GUILD_CATEGORY}
							<Badge>Category</Badge>
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
		padding: var(--space-10) var(--space-6);
		max-width: var(--size-reader-max);
		margin: 0 auto;
	}

	.page-header {
		margin-bottom: var(--space-8);
	}

	.page-header h1 {
		font: var(--type-display-lg);
		letter-spacing: var(--tracking-display-lg);
		margin-bottom: var(--space-2);
	}

	.header-sub {
		font: var(--type-body-md);
		color: var(--text-secondary);
	}

	.header-sub strong {
		color: var(--text-primary);
		font-weight: 600;
	}

	.channels-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: var(--space-3);
	}

	.channel-card {
		display: flex;
		flex-direction: column;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		padding: var(--space-4) var(--space-5);
		color: inherit;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint);
	}

	.channel-card:hover {
		background: var(--bg-raised);
		border-color: var(--border-default);
		color: inherit;
	}

	.skeleton-card {
		gap: var(--space-3);
	}

	.channel-header {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
		color: var(--text-tertiary);
	}

	.channel-name {
		font: var(--type-heading-sm);
		color: var(--text-primary);
	}

	.channel-topic {
		font: var(--type-body-sm);
		color: var(--text-secondary);
		margin-bottom: var(--space-4);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.channel-stats {
		margin-top: auto;
	}

	.stat-bar-bg {
		height: 4px;
		background: var(--bg-raised);
		border-radius: var(--radius-full);
		overflow: hidden;
		margin-bottom: var(--space-2);
	}

	.stat-bar-fill {
		height: 100%;
		background: var(--accent);
		border-radius: var(--radius-full);
		min-width: 2px;
	}

	.stat-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-2);
	}

	.stat-count {
		font: var(--type-mono-sm);
		color: var(--text-secondary);
	}

	.stat-date {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}
</style>
