<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';
	import { getAuthorMessages, getGuilds, getUserProfile } from '#lib/api.ts';
	import type { Guild, UserProfile, Message } from '#lib/types.ts';
	import StatCard from '#lib/components/StatCard.svelte';
	import MessageCard from '#lib/components/MessageCard.svelte';

	let guild: Guild | null = $state(null);
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
			const guilds = await getGuilds();
			if (guilds.length > 0) {
				guild = guilds[0];
			}
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
		<div class="center-state">
			<div class="spinner"></div>
			<span class="mono">Loading profile...</span>
		</div>
	{:else if error}
		<div class="center-state error">⚠ {error}</div>
	{:else if profile}
		<!-- Hero header -->
		<header class="profile-hero enter">
			<a href="/users" class="back-link mono">← All Users</a>
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
							<span class="badge accent">BOT</span>
						{/if}
						<span class="mono id-badge">{profile.id}</span>
					</div>
				</div>
			</div>
		</header>

		<!-- Key stats -->
		<section class="section enter">
			<h2 class="section-title">
				<span class="section-icon">◈</span>
				Overview
			</h2>
			<div class="stats-grid">
				<StatCard label="Messages" value={profile.total_messages} icon="✉" />
				<StatCard label="Attachments" value={profile.total_attachments} icon="📎" />
				<StatCard label="Reactions Received" value={profile.total_reactions_received} icon="♥" />
				<StatCard label="Active Channels" value={profile.active_channels} icon="≡" />
			</div>
		</section>

		<!-- Timeline line -->
		<section class="section enter">
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
					<span class="mono">Avg. message length: <strong>{profile.avg_message_length}</strong> chars</span>
				</div>
			</div>
		</section>

		<!-- Activity chart -->
		{#if profile.monthly_activity.length > 0}
			<section class="section enter">
				<h2 class="section-title">
					<span class="section-icon">▤</span>
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
			<section class="section enter">
				<h2 class="section-title">
					<span class="section-icon">≡</span>
					Top Channels
				</h2>
				<div class="bar-chart">
					{#each profile.top_channels as ch, i}
						{@const maxCount = profile.top_channels[0].message_count}
						<a href="/channel/{ch.channel_id}" class="bar-row" style="--i: {i}">
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
			<section class="section enter">
				<h2 class="section-title">
					<span class="section-icon">♥</span>
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
		<section class="section enter">
			<h2 class="section-title">
				<span class="section-icon">✉</span>
				Recent Messages
				<button class="toggle-btn" onclick={loadRecentMessages}>
					{#if loadingMessages}
						<div class="spinner small"></div>
					{:else if showMessages}
						Loaded
					{:else}
						Load Messages
					{/if}
				</button>
			</h2>

			{#if messagesError}
				<p class="mono" style="color: var(--danger); font-size: 13px;">⚠ {messagesError}</p>
			{/if}
			{#if showMessages && recentMessages.length > 0}
				<div class="messages-list">
					{#each recentMessages as msg (msg.id)}
						<MessageCard message={msg} />
					{/each}
				</div>
			{:else if showMessages}
				<p class="mono" style="color: var(--text-tertiary); font-size: 13px;">
					No recent messages found.
				</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.profile-page {
		max-width: var(--size-reader-max);
		margin: 0 auto;
		padding: var(--space-8) var(--space-6);
	}

	/* Hero */
	.profile-hero {
		margin-bottom: var(--space-10);
	}

	.back-link {
		display: inline-block;
		font-size: 13px;
		color: var(--text-tertiary);
		margin-bottom: var(--space-4);
		transition: color var(--duration-micro) var(--ease-out-quint);
	}

	.back-link:hover {
		color: var(--accent);
	}

	.hero-row {
		display: flex;
		align-items: center;
		gap: var(--space-6);
	}

	.hero-avatar {
		width: 80px;
		height: 80px;
		border-radius: 50%;
		object-fit: cover;
		border: 3px solid var(--border-default);
		flex-shrink: 0;
	}

	.hero-avatar.avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-secondary);
		font-weight: 700;
		font-size: 32px;
	}

	.hero-info {
		min-width: 0;
	}

	.hero-name {
		font-size: 36px;
		font-weight: 700;
		letter-spacing: -0.04em;
		line-height: 1.1;
		margin-bottom: var(--space-2);
		color: var(--text-primary);
	}


	.hero-meta {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		font-size: 14px;
		color: var(--text-secondary);
		flex-wrap: wrap;
	}

	.id-badge {
		font-size: 11px;
		color: var(--text-tertiary);
		padding: 1px 6px;
		background: var(--bg-raised);
		border-radius: var(--radius-xs);
	}

	/* Sections */
	.section {
		margin-bottom: var(--space-10);
	}

	.section-title {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: var(--space-5);
	}

	.section-icon { color: var(--accent); font-size: 14px; }

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: var(--space-4);
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
		font-size: 11px;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.timeline-value {
		font-size: 14px;
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
		font-size: 12px;
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	.timeline-extra {
		width: 100%;
		padding-top: var(--space-2);
		margin-top: var(--space-2);
		border-top: 1px solid var(--border-subtle);
		font-size: 13px;
		color: var(--text-tertiary);
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
		background: linear-gradient(180deg, var(--accent), var(--accent-strong));
		border-radius: 3px 3px 0 0;
		transition: height var(--duration-large) var(--ease-out-quint);
		min-height: 2px;
	}

	.chart-col:hover .chart-bar {
		background: var(--accent);
		filter: brightness(1.2);
	}

	.chart-label {
		font-size: 9px;
		color: var(--text-tertiary);
		margin-top: var(--space-1);
		writing-mode: vertical-lr;
		transform: rotate(180deg);
		white-space: nowrap;
	}

	/* Bar chart (channels) */
	.bar-chart {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.bar-row {
		display: grid;
		grid-template-columns: 160px 1fr 80px;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-sm);
		transition: background var(--duration-micro) var(--ease-out-quint);
		animation: enter var(--duration-medium) var(--ease-out-quint) both;
		animation-delay: calc(min(var(--i, 0), var(--stagger-max)) * var(--stagger));
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
		background: linear-gradient(90deg, var(--accent-strong), var(--accent));
		border-radius: 4px;
		transition: width var(--duration-large) var(--ease-out-quint);
	}

	.bar-value { font-size: 13px; color: var(--text-tertiary); text-align: right; }

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
		border-radius: var(--radius-sm);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.reaction-chip:hover {
		border-color: var(--border-default);
	}

	.reaction-emoji {
		font-size: 20px;
	}

	.reaction-count {
		font-size: 13px;
		color: var(--text-secondary);
	}

	/* Messages */
	.toggle-btn {
		margin-left: auto;
		padding: var(--space-1) var(--space-3);
		font-size: 12px;
		font-weight: 500;
		color: var(--accent);
		background: var(--accent-muted);
		border: 1px solid var(--accent-glow);
		border-radius: var(--radius-xs);
		display: flex;
		align-items: center;
		gap: var(--space-2);
		transition: all var(--duration-micro) var(--ease-out-quint);
	}

	.toggle-btn:hover {
		background: var(--accent);
		color: var(--bg-canvas);
	}

	.messages-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	/* States */
	.center-state {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		justify-content: center;
		padding: var(--space-16) 0;
		color: var(--text-tertiary);
	}

	.center-state.error {
		color: var(--danger);
	}

	.spinner {
		width: 20px;
		height: 20px;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.spinner.small {
		width: 14px;
		height: 14px;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
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

		.hero-name {
			font-size: 28px;
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
