<!--
	Overview: the selected guild at a glance. A hero, four stat tiles with their change
	since the last completed scrape job (none when there is no such job), messages per
	month, the most active channels and top contributors side by side, and the archive's
	health, which leads to the Archive screen.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { getDownloadStats, getGuildActivity, getStats } from '#lib/api.ts';
	import { channelHref, personHref } from '#lib/routes.ts';
	import { scrapeStatus } from '#lib/scrape-status.svelte.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { DownloadStatsResponse, GuildActivity, Stats } from '#lib/types.ts';
	import ActivityChart from '#lib/components/ActivityChart.svelte';
	import ArchiveHealth from '#lib/components/ArchiveHealth.svelte';
	import StatCard from '#lib/components/StatCard.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	const guild = shell.guild;
	let stats = $state<Stats | null>(null);
	let activity = $state<GuildActivity | null>(null);
	let downloads = $state<DownloadStatsResponse | null>(null);
	let downloadsError = $state('');
	let loading = $state(true);
	let error = $state(shell.guildsError);

	onMount(async () => {
		if (!guild) {
			loading = false;
			return;
		}
		// Download stats and scrape status only feed the health card; it says when they fail.
		const health = Promise.all([
			getDownloadStats()
				.then((d) => (downloads = d))
				.catch((e) => (downloadsError = e instanceof Error ? e.message : 'Download stats unavailable')),
			scrapeStatus.load()
		]);
		try {
			[stats, activity] = await Promise.all([getStats(guild.id), getGuildActivity(guild.id)]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load data';
		} finally {
			loading = false;
		}
		await health;
	});

	/** The archive stores naive UTC times; read one as UTC. */
	function archiveTime(iso: string): Date {
		return new Date(/(Z|[+-]\d\d:\d\d)$/.test(iso) ? iso : `${iso}Z`);
	}

	function formatDate(iso: string): string {
		return archiveTime(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
	}

	const since = $derived(stats?.since_last_scrape ?? null);
	const changeTitle = $derived(
		since ? `Since the last completed scrape job started, ${formatDate(since.started_at)}` : undefined
	);
	const tiles = $derived(
		stats
			? [
					{ label: 'Messages', value: stats.total_messages, icon: 'message', change: since?.messages },
					{ label: 'Channels', value: stats.total_channels, icon: 'hash', change: since?.channels },
					{ label: 'Authors', value: stats.total_users, icon: 'users', change: since?.authors },
					{ label: 'Attachments', value: stats.total_attachments, icon: 'paperclip', change: since?.attachments }
				] as const
			: []
	);
	const topChannelMax = $derived(Math.max(1, ...(stats?.top_channels.map((c) => c.message_count) ?? [])));
	const topUserMax = $derived(Math.max(1, ...(stats?.top_users.map((u) => u.message_count) ?? [])));
</script>

<div class="overview">
	{#if error}
		<Alert tone="danger" title="The archive could not be loaded">
			<p>{error}</p>
			<p>Make sure the API server is running: <code>wumpus-archiver serve archive.db</code></p>
		</Alert>
	{:else if !guild}
		<EmptyState
			icon="archive"
			title="Nothing archived yet"
			description="Scrape a guild from the Archive screen and it will show up here."
		/>
	{:else}
		<header class="hero">
			{#if guild.icon_url}
				<img class="guild-icon" src={guild.icon_url} alt="" />
			{:else}
				<span class="guild-icon fallback" aria-hidden="true">{guild.name.slice(0, 1).toUpperCase()}</span>
			{/if}
			<div class="hero-text">
				<h1 class="guild-name">{guild.name}</h1>
				<p class="hero-meta">
					{#if guild.last_scraped_at}
						<span>Scraped <time datetime={guild.last_scraped_at}>{formatDate(guild.last_scraped_at)}</time></span>
					{:else}
						<span>Never scraped</span>
					{/if}
					{#if guild.member_count !== null}
						<span>{guild.member_count.toLocaleString()} members at scrape</span>
					{/if}
					{#if guild.first_scraped_at}
						<span>Archived since {formatDate(guild.first_scraped_at)}</span>
					{/if}
				</p>
			</div>
		</header>

		{#if loading}
			<div class="loading" aria-busy="true">
				<span class="sr-only" role="status">Loading the overview…</span>
				<div class="stats-grid">
					{#each [0, 1, 2, 3] as i (i)}
						<div class="tile-skeleton">
							<Skeleton width="72px" height="10px" />
							<Skeleton width="96px" height="28px" />
						</div>
					{/each}
				</div>
				<div class="card"><Skeleton height="220px" radius="sm" /></div>
			</div>
		{:else if stats}
			<section class="stats-grid" aria-label="Totals">
				{#each tiles as tile, i (tile.label)}
					<StatCard
						label={tile.label}
						value={tile.value}
						icon={tile.icon}
						index={i}
						countUp
						change={tile.change ?? null}
						changeLabel="since last scrape"
						{changeTitle}
					/>
				{/each}
			</section>

			<section class="card enter" style:--i={4}>
				<ActivityChart buckets={activity?.buckets ?? []} />
			</section>

			<div class="columns">
				<section class="card list-card enter" style:--i={5} aria-labelledby="channels-title">
					<h2 id="channels-title" class="card-title">
						<Icon name="chart" />
						Most Active Channels
					</h2>
					{#if stats.top_channels.length === 0}
						<p class="empty">No channel holds messages yet.</p>
					{:else}
						<ol class="rows">
							{#each stats.top_channels as ch (ch.id)}
								<li>
									<a href={channelHref(ch.id)} class="bar-row">
										<span class="bar-label truncate">#{ch.name}</span>
										<span class="bar-track" aria-hidden="true">
											<span class="bar-fill" style:width="{(ch.message_count / topChannelMax) * 100}%"></span>
										</span>
										<span class="bar-value mono">{ch.message_count.toLocaleString()}</span>
									</a>
								</li>
							{/each}
						</ol>
					{/if}
				</section>

				<section class="card list-card enter" style:--i={6} aria-labelledby="people-title">
					<h2 id="people-title" class="card-title">
						<Icon name="users" />
						Top Contributors
					</h2>
					{#if stats.top_users.length === 0}
						<p class="empty">Nobody has posted yet.</p>
					{:else}
						<ol class="rows">
							{#each stats.top_users as user, i (user.id)}
								<li>
									<a href={personHref(user.id)} class="person-row">
										<span class="rank mono">{i + 1}</span>
										{#if user.avatar_url}
											<img class="avatar" src={user.avatar_url} alt="" />
										{:else}
											<span class="avatar fallback" aria-hidden="true">{(user.username || '?')[0].toUpperCase()}</span>
										{/if}
										<span class="person-name">
											<span class="display-name truncate">{user.display_name}</span>
											<span class="handle mono truncate">@{user.username}</span>
										</span>
										<span class="share" aria-hidden="true">
											<span class="share-fill" style:width="{(user.message_count / topUserMax) * 100}%"></span>
										</span>
										<span class="bar-value mono">{user.message_count.toLocaleString()}</span>
									</a>
								</li>
							{/each}
						</ol>
					{/if}
				</section>
			</div>

			<div class="enter" style:--i={7}>
				<ArchiveHealth {guild} {downloads} {downloadsError} status={scrapeStatus.status} sinceLastScrape={since} />
			</div>
		{/if}
	{/if}
</div>

<style>
	.overview {
		max-width: 1120px;
		margin: 0 auto;
		padding: var(--space-10) var(--space-6);
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.hero {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		margin-bottom: var(--space-2);
	}

	.guild-icon {
		width: 56px;
		height: 56px;
		flex-shrink: 0;
		border-radius: var(--radius-lg);
		object-fit: cover;
	}

	.guild-icon.fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--accent-muted);
		color: var(--accent);
		font: var(--type-heading-lg);
	}

	.hero-text {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		min-width: 0;
	}

	.guild-name {
		font: var(--type-display-lg);
		letter-spacing: var(--tracking-display-lg);
		color: var(--text-primary);
		overflow-wrap: anywhere;
	}

	.hero-meta {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.hero-meta > span + span::before {
		content: '·';
		margin-right: var(--space-2);
		color: var(--text-tertiary);
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: var(--space-3);
	}

	.loading {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
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

	.card {
		padding: var(--space-5);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		min-width: 0;
	}

	.columns {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: var(--space-3);
	}

	.card-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-heading-sm);
		color: var(--text-primary);
		margin-bottom: var(--space-3);
	}

	.card-title :global(.icon) {
		color: var(--text-secondary);
	}

	.empty {
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.rows {
		list-style: none;
		margin: 0 calc(-1 * var(--space-2));
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.bar-row,
	.person-row {
		display: grid;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-2);
		border-radius: var(--radius-sm);
		color: inherit;
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.bar-row {
		grid-template-columns: minmax(0, 9rem) minmax(0, 1fr) 4.5rem;
	}

	.person-row {
		grid-template-columns: 1.25rem 28px minmax(0, 1fr) minmax(0, 5rem) 4.5rem;
	}

	.bar-row:hover,
	.person-row:hover {
		background: var(--bg-hover);
		color: inherit;
	}

	.bar-label {
		font: var(--type-body-md);
		color: var(--text-secondary);
	}

	.bar-row:hover .bar-label {
		color: var(--text-primary);
	}

	.bar-track,
	.share {
		display: block;
		height: 6px;
		background: var(--bg-raised);
		border-radius: var(--radius-full);
		overflow: hidden;
	}

	.bar-fill,
	.share-fill {
		display: block;
		height: 100%;
		background: var(--accent);
		border-radius: var(--radius-full);
	}

	.share-fill {
		background: var(--text-tertiary);
	}

	.bar-value {
		font: var(--type-mono-md);
		color: var(--text-secondary);
		text-align: right;
		font-variant-numeric: tabular-nums;
	}

	.rank {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		text-align: right;
	}

	.avatar {
		width: 28px;
		height: 28px;
		border-radius: var(--radius-full);
		object-fit: cover;
	}

	.avatar.fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-secondary);
		font: var(--type-label-sm);
	}

	.person-name {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.display-name {
		font: var(--type-label-md);
		color: var(--text-primary);
	}

	.handle {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	@media (max-width: 900px) {
		.stats-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.columns {
			grid-template-columns: minmax(0, 1fr);
		}
	}

	@media (max-width: 600px) {
		.overview {
			padding: var(--space-6) var(--space-4);
		}

		.guild-name {
			font: var(--type-heading-lg);
		}

		.hero-meta {
			flex-direction: column;
			gap: 0;
		}

		.hero-meta > span + span::before {
			content: none;
		}

		.person-row {
			grid-template-columns: 1.25rem 28px minmax(0, 1fr) 4rem;
		}

		.share {
			display: none;
		}
	}
</style>
