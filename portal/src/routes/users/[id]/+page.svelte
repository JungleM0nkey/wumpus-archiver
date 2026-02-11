<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getGuilds, getUserProfile, searchMessages } from '$lib/api';
	import type { Guild, UserProfile, Message } from '$lib/types';
	import StatCard from '$lib/components/StatCard.svelte';
	import MessageCard from '$lib/components/MessageCard.svelte';

	let guild: Guild | null = $state(null);
	let profile: UserProfile | null = $state(null);
	let recentMessages: Message[] = $state([]);
	let loading = $state(true);
	let error = $state('');
	let showMessages = $state(false);
	let loadingMessages = $state(false);

	const userId = $derived(page.params.id);

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
		if (showMessages || !profile) return;
		loadingMessages = true;
		try {
			const res = await searchMessages('', {
				guild_id: guild?.id,
				limit: 20,
			});
			// searchMessages requires a query, so we use author_id filter via direct fetch
			const params = new URLSearchParams({ q: ' ', author_id: userId, limit: '20' });
			if (guild) params.set('guild_id', guild.id);
			const r = await fetch(`/api/search?${params}`);
			if (r.ok) {
				const data = await r.json();
				recentMessages = data.results.map((sr: { message: Message }) => sr.message);
			}
		} catch {
			// Silent fail for messages
		} finally {
			loadingMessages = false;
			showMessages = true;
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
		<header class="profile-hero fade-in">
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
					<h1 class="hero-name serif">
						{profile.display_name || profile.username}<span class="dot">.</span>
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
		<section class="section fade-in" style="animation-delay: 50ms">
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
		<section class="section fade-in" style="animation-delay: 100ms">
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
			<section class="section fade-in" style="animation-delay: 150ms">
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
			<section class="section fade-in" style="animation-delay: 200ms">
				<h2 class="section-title">
					<span class="section-icon">≡</span>
					Top Channels
				</h2>
				<div class="bar-chart">
					{#each profile.top_channels as ch, i}
						{@const maxCount = profile.top_channels[0].message_count}
						<a href="/channel/{ch.channel_id}" class="bar-row" style="animation-delay: {i * 30}ms">
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
			<section class="section fade-in" style="animation-delay: 250ms">
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
		<section class="section fade-in" style="animation-delay: 300ms">
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

			{#if showMessages && recentMessages.length > 0}
				<div class="messages-list">
					{#each recentMessages as msg (msg.id)}
						<MessageCard message={msg} />
					{/each}
				</div>
			{:else if showMessages}
				<p class="mono" style="color: var(--text-muted); font-size: 13px;">
					No recent messages found with content.
				</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.profile-page {
		max-width: var(--max-content);
		margin: 0 auto;
		padding: var(--sp-8) var(--sp-6);
	}

	/* Hero */
	.profile-hero {
		margin-bottom: var(--sp-10);
	}

	.back-link {
		display: inline-block;
		font-size: 13px;
		color: var(--text-muted);
		margin-bottom: var(--sp-4);
		transition: color 0.15s var(--ease-out);
	}

	.back-link:hover {
		color: var(--accent-text);
	}

	.hero-row {
		display: flex;
		align-items: center;
		gap: var(--sp-6);
	}

	.hero-avatar {
		width: 80px;
		height: 80px;
		border-radius: 50%;
		object-fit: cover;
		border: 3px solid var(--border-strong);
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
		margin-bottom: var(--sp-2);
		color: var(--text-primary);
	}

	.dot { color: var(--accent); }

	.hero-meta {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		font-size: 14px;
		color: var(--text-secondary);
		flex-wrap: wrap;
	}

	.id-badge {
		font-size: 11px;
		color: var(--text-faint);
		padding: 1px 6px;
		background: var(--bg-raised);
		border-radius: var(--radius-sm);
	}

	/* Sections */
	.section {
		margin-bottom: var(--sp-10);
	}

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
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: var(--sp-4);
	}

	/* Timeline summary */
	.timeline-summary {
		display: flex;
		align-items: center;
		gap: var(--sp-4);
		padding: var(--sp-5);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		flex-wrap: wrap;
	}

	.timeline-item {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.timeline-label {
		font-size: 11px;
		color: var(--text-muted);
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
		gap: var(--sp-2);
		min-width: 100px;
	}

	.timeline-line {
		flex: 1;
		height: 1px;
		background: var(--border-strong);
	}

	.timeline-days {
		font-size: 12px;
		color: var(--text-muted);
		white-space: nowrap;
	}

	.timeline-extra {
		width: 100%;
		padding-top: var(--sp-2);
		margin-top: var(--sp-2);
		border-top: 1px solid var(--border);
		font-size: 13px;
		color: var(--text-muted);
	}

	/* Activity chart */
	.activity-chart {
		padding: var(--sp-4);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
	}

	.chart-bars {
		display: flex;
		align-items: flex-end;
		gap: 3px;
		height: 140px;
		padding-bottom: var(--sp-5);
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
		background: linear-gradient(180deg, var(--accent), var(--accent-dim));
		border-radius: 3px 3px 0 0;
		transition: height 0.4s var(--ease-out);
		min-height: 2px;
	}

	.chart-col:hover .chart-bar {
		background: var(--accent);
		filter: brightness(1.2);
	}

	.chart-label {
		font-size: 9px;
		color: var(--text-faint);
		margin-top: var(--sp-1);
		writing-mode: vertical-lr;
		transform: rotate(180deg);
		white-space: nowrap;
	}

	/* Bar chart (channels) */
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

	/* Reactions */
	.reactions-grid {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-2);
	}

	.reaction-chip {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-2) var(--sp-3);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		transition: border-color 0.15s var(--ease-out);
	}

	.reaction-chip:hover {
		border-color: var(--border-strong);
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
		padding: var(--sp-1) var(--sp-3);
		font-size: 12px;
		font-weight: 500;
		color: var(--accent-text);
		background: var(--accent-glow);
		border: 1px solid var(--border-accent);
		border-radius: var(--radius-sm);
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		transition: all 0.15s var(--ease-out);
	}

	.toggle-btn:hover {
		background: var(--accent);
		color: var(--bg-base);
	}

	.messages-list {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
	}

	/* States */
	.center-state {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		justify-content: center;
		padding: var(--sp-16) 0;
		color: var(--text-muted);
	}

	.center-state.error {
		color: var(--error);
	}

	.spinner {
		width: 20px;
		height: 20px;
		border: 2px solid var(--border);
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
