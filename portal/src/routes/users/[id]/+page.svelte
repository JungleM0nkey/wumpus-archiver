<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';
	import { getAuthorMessages, getUserProfile } from '#lib/api.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { UserProfile, Message } from '#lib/types.ts';
	import StatCard from '#lib/components/StatCard.svelte';
	import MessageCard from '#lib/components/MessageCard.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import Button from '#lib/components/ui/Button.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	const guild = shell.guild;
	let profile: UserProfile | null = $state(null);
	let recentMessages: Message[] = $state([]);
	let loading = $state(true);
	let error = $state('');
	let showMessages = $state(false);
	let loadingMessages = $state(false);
	let messagesError = $state('');

	let { params }: PageProps = $props();
	const userId = $derived(params.id);

	onMount(async () => {
		try {
			profile = await getUserProfile(userId, {
				guild_id: guild?.id,
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load user profile';
		} finally {
			loading = false;
		}
	});

	async function loadRecentMessages() {
		if (showMessages || loadingMessages || !profile) return;
		loadingMessages = true;
		messagesError = '';
		try {
			const res = await getAuthorMessages(userId, { guild_id: guild?.id, limit: 20 });
			recentMessages = res.results.map((result) => result.message);
			showMessages = true;
		} catch (e) {
			messagesError = e instanceof Error ? e.message : 'Failed to load recent messages';
		} finally {
			loadingMessages = false;
		}
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleDateString('en-US', {
			month: 'long',
			day: 'numeric',
			year: 'numeric',
		});
	}

	function formatDateShort(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
		});
	}

	function daysActive(): string {
		if (!profile?.first_message_at || !profile?.last_message_at) return '—';
		const first = new Date(profile.first_message_at);
		const last = new Date(profile.last_message_at);
		const days = Math.ceil((last.getTime() - first.getTime()) / (1000 * 60 * 60 * 24));
		return days.toLocaleString();
	}

	function maxActivity(): number {
		if (!profile?.monthly_activity.length) return 1;
		return Math.max(...profile.monthly_activity.map((m) => m.count), 1);
	}
</script>

<div class="profile-page">
	{#if loading}
		<div class="profile-skeleton" aria-busy="true">
			<span class="sr-only" role="status">Loading profile…</span>
			<div class="hero-row">
				<Skeleton width="80px" height="80px" radius="full" />
				<div class="hero-info skeleton-lines">
					<Skeleton width="220px" height="32px" />
					<Skeleton width="160px" height="12px" />
				</div>
			</div>
			<div class="stats-grid">
				{#each [0, 1, 2, 3] as i (i)}
					<Skeleton height="96px" radius="md" />
				{/each}
			</div>
		</div>
	{:else if error}
		<Alert tone="danger" title="The profile could not be loaded">{error}</Alert>
	{:else if profile}
		<!-- Hero header -->
		<header class="profile-hero enter">
			<a href="/users" class="back-link"><Icon name="arrow-left" size={14} /> People</a>
			<div class="hero-row">
				{#if profile.avatar_url}
					<img
						class="hero-avatar"
						src={profile.avatar_url}
						alt={profile.display_name || profile.username}
					/>
				{:else}
					<div class="hero-avatar avatar-fallback">
						{(profile.username || '?')[0].toUpperCase()}
					</div>
				{/if}
				<div class="hero-info">
					<h1 class="hero-name">
						{profile.display_name || profile.username}
					</h1>
					<div class="hero-meta">
						<span class="mono">@{profile.username}</span>
						{#if profile.discriminator && profile.discriminator !== '0'}
							<span class="mono">#{profile.discriminator}</span>
						{/if}
						{#if profile.bot}
							<Badge tone="accent">BOT</Badge>
						{/if}
						<Badge mono>{profile.id}</Badge>
					</div>
				</div>
			</div>
		</header>

		<!-- Key stats -->
		<section class="section">
			<h2 class="section-title">
				<Icon name="dashboard" />
				Overview
			</h2>
			<div class="stats-grid">
				<StatCard label="Messages" value={profile.total_messages} icon="message" index={0} />
				<StatCard label="Attachments" value={profile.total_attachments} icon="paperclip" index={1} />
				<StatCard label="Reactions Received" value={profile.total_reactions_received} icon="heart" index={2} />
				<StatCard label="Active Channels" value={profile.active_channels} icon="hash" index={3} />
			</div>
		</section>

		<!-- Timeline line -->
		<section class="section enter" style:--i={4}>
			<div class="timeline-summary">
				<div class="timeline-item">
					<span class="timeline-label">First Message</span>
					<span class="timeline-value mono">{formatDate(profile.first_message_at)}</span>
				</div>
				<div class="timeline-divider">
					<div class="timeline-line"></div>
					<span class="timeline-days mono">{daysActive()} days</span>
					<div class="timeline-line"></div>
				</div>
				<div class="timeline-item">
					<span class="timeline-label">Last Message</span>
					<span class="timeline-value mono">{formatDate(profile.last_message_at)}</span>
				</div>
				<div class="timeline-extra">
					Avg. message length: <strong class="mono">{profile.avg_message_length}</strong> chars
				</div>
			</div>
		</section>

		<!-- Activity chart -->
		{#if profile.monthly_activity.length > 0}
			<section class="section">
				<h2 class="section-title">
					<Icon name="chart" />
					Monthly Activity
				</h2>
				<div class="activity-chart">
					<div class="chart-bars">
						{#each profile.monthly_activity as month}
							{@const height = (month.count / maxActivity()) * 100}
							<div class="chart-col" title="{month.label}: {month.count} messages">
								<div class="chart-bar" style="height: {Math.max(height, 2)}%"></div>
								<span class="chart-label mono">{month.label.split(' ')[0].slice(0, 3)}</span>
							</div>
						{/each}
					</div>
				</div>
			</section>
		{/if}

		<!-- Top channels -->
		{#if profile.top_channels.length > 0}
			<section class="section">
				<h2 class="section-title">
					<Icon name="hash" />
					Top Channels
				</h2>
				<div class="bar-chart">
					{#each profile.top_channels as ch, i (ch.channel_id)}
						{@const maxCount = profile.top_channels[0].message_count}
						<a href="/channel/{ch.channel_id}" class="bar-row enter" style:--i={i}>
							<span class="bar-label truncate">#{ch.channel_name}</span>
							<div class="bar-track">
								<div
									class="bar-fill"
									style="width: {(ch.message_count / maxCount) * 100}%"
								></div>
							</div>
							<span class="bar-value mono">{ch.message_count.toLocaleString()}</span>
						</a>
					{/each}
				</div>
			</section>
		{/if}

		<!-- Top reactions received -->
		{#if profile.top_reactions_received.length > 0}
			<section class="section">
				<h2 class="section-title">
					<Icon name="heart" />
					Top Reactions Received
				</h2>
				<div class="reactions-grid">
					{#each profile.top_reactions_received as react}
						<div class="reaction-chip">
							<span class="reaction-emoji">{react.emoji}</span>
							<span class="reaction-count mono">×{react.count.toLocaleString()}</span>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<!-- Recent messages toggle -->
		<section class="section">
			<h2 class="section-title">
				<Icon name="message" />
				Recent Messages
				<span class="toggle">
					<Button size="sm" loading={loadingMessages} onclick={loadRecentMessages}>
						{showMessages ? 'Loaded' : 'Load Messages'}
					</Button>
				</span>
			</h2>

			{#if messagesError}
				<Alert tone="danger" title="Recent messages could not be loaded">{messagesError}</Alert>
			{/if}
			{#if showMessages && recentMessages.length > 0}
				<div class="messages-list">
					{#each recentMessages as msg (msg.id)}
						<MessageCard message={msg} />
					{/each}
				</div>
			{:else if showMessages}
				<EmptyState icon="inbox" title="No recent messages found." compact />
			{/if}
		</section>
	{/if}
</div>

<style>
	.profile-page {
		max-width: var(--size-reader-max);
		margin: 0 auto;
		padding: var(--space-10) var(--space-6);
	}

	/* Hero */
	.profile-hero {
		margin-bottom: var(--space-10);
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-label-sm);
		color: var(--text-tertiary);
		margin-bottom: var(--space-4);
	}

	.back-link:hover {
		color: var(--text-primary);
	}

	.hero-row {
		display: flex;
		align-items: center;
		gap: var(--space-6);
	}

	.hero-avatar {
		width: 80px;
		height: 80px;
		border-radius: var(--radius-full);
		object-fit: cover;
		border: 1px solid var(--border-default);
		flex-shrink: 0;
	}

	.hero-avatar.avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-secondary);
		font: var(--type-display-lg);
	}

	.hero-info {
		min-width: 0;
	}

	.hero-name {
		font: var(--type-display-lg);
		letter-spacing: var(--tracking-display-lg);
		margin-bottom: var(--space-2);
		color: var(--text-primary);
	}

	.hero-meta {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		font: var(--type-mono-md);
		color: var(--text-secondary);
		flex-wrap: wrap;
	}

	.profile-skeleton {
		display: flex;
		flex-direction: column;
		gap: var(--space-10);
	}

	.skeleton-lines {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	/* Sections */
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

	/* Timeline summary */
	.timeline-summary {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-5);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		flex-wrap: wrap;
	}

	.timeline-item {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.timeline-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.timeline-value {
		font: var(--type-mono-md);
		color: var(--text-primary);
	}

	.timeline-divider {
		flex: 1;
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 100px;
	}

	.timeline-line {
		flex: 1;
		height: 1px;
		background: var(--border-default);
	}

	.timeline-days {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	.timeline-extra {
		width: 100%;
		padding-top: var(--space-3);
		margin-top: var(--space-1);
		border-top: 1px solid var(--border-subtle);
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.timeline-extra strong {
		color: var(--text-primary);
		font-weight: 500;
	}

	/* Activity chart */
	.activity-chart {
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
	}

	.chart-bars {
		display: flex;
		align-items: flex-end;
		gap: 3px;
		height: 140px;
		padding-bottom: var(--space-5);
	}

	.chart-col {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		height: 100%;
		justify-content: flex-end;
		min-width: 0;
	}

	.chart-bar {
		width: 100%;
		max-width: 32px;
		background: var(--accent);
		border-radius: var(--radius-xs) var(--radius-xs) 0 0;
		min-height: 2px;
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.chart-col:hover .chart-bar {
		background: var(--accent-strong);
	}

	.chart-label {
		font-size: 9px;
		color: var(--text-tertiary);
		margin-top: var(--space-1);
		writing-mode: vertical-lr;
		rotate: 180deg;
		white-space: nowrap;
	}

	/* Bar chart (channels) */
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

	/* Reactions */
	.reactions-grid {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.reaction-chip {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-full);
	}

	.reaction-emoji {
		font-size: 18px;
		line-height: 1;
	}

	.reaction-count {
		font: var(--type-mono-md);
		color: var(--text-secondary);
	}

	/* Messages */
	.toggle {
		margin-left: auto;
	}

	.messages-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	@media (max-width: 768px) {
		.hero-row {
			flex-direction: column;
			align-items: flex-start;
		}

		.hero-avatar {
			width: 64px;
			height: 64px;
		}

		.stats-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.timeline-summary {
			flex-direction: column;
			align-items: stretch;
		}

		.timeline-divider {
			min-width: auto;
		}

		.bar-row {
			grid-template-columns: 120px 1fr 60px;
		}

		.chart-label {
			display: none;
		}
	}
</style>
