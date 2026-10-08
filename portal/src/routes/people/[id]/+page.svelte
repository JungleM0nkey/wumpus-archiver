<!--
	A person's profile in the selected guild: who they are and when they were active,
	four stat tiles, 52 weeks of activity as a heatmap, the channels they post in most,
	the reactions their messages received and their newest messages, each opening the
	channel on that message.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';
	import { ApiError, getAuthorMessages, getUserProfile } from '#lib/api.ts';
	import { channelHref } from '#lib/routes.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { SearchResult, UserProfile } from '#lib/types.ts';
	import ActivityHeatmap from '#lib/components/ActivityHeatmap.svelte';
	import StatCard from '#lib/components/StatCard.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Avatar from '#lib/components/ui/Avatar.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	const RECENT_MESSAGES = 10;

	let { params }: PageProps = $props();
	const userId = $derived(params.id);
	const guild = shell.guild;

	let profile = $state<UserProfile | null>(null);
	let loading = $state(true);
	let error = $state('');
	let missing = $state(false);

	let recent = $state<SearchResult[]>([]);
	let recentLoading = $state(true);
	let recentError = $state('');

	async function loadProfile() {
		try {
			profile = await getUserProfile(userId, { guild_id: guild?.id });
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) missing = true;
			else error = e instanceof Error ? e.message : 'The profile could not be loaded';
		} finally {
			loading = false;
		}
	}

	async function loadRecent() {
		try {
			const res = await getAuthorMessages(userId, { guild_id: guild?.id, limit: RECENT_MESSAGES });
			recent = res.results;
		} catch (e) {
			recentError = e instanceof Error ? e.message : 'The recent messages could not be loaded';
		} finally {
			recentLoading = false;
		}
	}

	onMount(() => {
		void loadProfile();
		void loadRecent();
	});

	const name = $derived(profile ? profile.display_name || profile.username : '');

	function formatDay(iso: string): string {
		return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
	}

	function formatMoment(iso: string): string {
		return new Date(iso).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	function plural(count: number, one: string, many: string): string {
		return `${count.toLocaleString()} ${count === 1 ? one : many}`;
	}
</script>

<div class="profile-page">
	<nav class="breadcrumb" aria-label="Breadcrumb">
		<ol>
			<li><a href="/people">People</a></li>
			<li aria-hidden="true"><Icon name="chevron-right" size={14} /></li>
			<li aria-current="page" class="truncate">
				{#if profile}{name}{:else if loading}<Skeleton width="80px" height="12px" />{:else}Unknown{/if}
			</li>
		</ol>
	</nav>

	{#if loading}
		<div class="profile-skeleton" aria-busy="true">
			<span class="sr-only" role="status">Loading profile…</span>
			<div class="hero">
				<Skeleton width="72px" height="72px" radius="full" />
				<div class="skeleton-lines">
					<Skeleton width="220px" height="32px" />
					<Skeleton width="260px" height="12px" />
				</div>
			</div>
			<div class="stats-grid">
				{#each [0, 1, 2, 3] as i (i)}
					<Skeleton height="96px" radius="md" />
				{/each}
			</div>
			<Skeleton height="96px" radius="md" />
		</div>
	{:else if missing}
		<EmptyState icon="users" title="This person is not in the archive." description="They may have no messages archived yet.">
			<a href="/people">Back to People</a>
		</EmptyState>
	{:else if error}
		<Alert tone="danger" title="The profile could not be loaded">{error}</Alert>
	{:else if profile}
		<header class="hero enter">
			<Avatar src={profile.avatar_url} {name} size={72} />
			<div class="hero-info">
				<h1>{name}</h1>
				<p class="hero-meta">
					<span class="mono">@{profile.username}</span>
					{#if profile.bot}<Badge tone="accent">BOT</Badge>{/if}
					{#if profile.first_message_at && profile.last_message_at}
						<span class="active">
							Active
							<time class="mono" datetime={profile.first_message_at}>{formatDay(profile.first_message_at)}</time>
							–
							<time class="mono" datetime={profile.last_message_at}>{formatDay(profile.last_message_at)}</time>
						</span>
					{/if}
				</p>
			</div>
		</header>

		<section class="section" aria-label="Totals">
			<div class="stats-grid">
				<StatCard
					label="Messages"
					value={profile.total_messages}
					icon="message"
					sub={profile.total_messages ? `${profile.avg_message_length} chars on average` : ''}
					index={0}
				/>
				<StatCard label="Attachments" value={profile.total_attachments} icon="paperclip" index={1} />
				<StatCard label="Reactions received" value={profile.total_reactions_received} icon="heart" index={2} />
				<StatCard label="Active channels" value={profile.active_channels} icon="hash" index={3} />
			</div>
		</section>

		<section class="section" aria-labelledby="activity-title">
			<h2 id="activity-title" class="section-title"><Icon name="chart" /> Activity</h2>
			<ActivityHeatmap weeks={profile.weekly_activity} label="{name}'s messages per week" />
		</section>

		<div class="columns">
			<section class="section" aria-labelledby="channels-title">
				<h2 id="channels-title" class="section-title"><Icon name="hash" /> Top channels</h2>
				{#if profile.top_channels.length}
					{@const most = profile.top_channels[0].message_count}
					<ol class="bars">
						{#each profile.top_channels as ch, i (ch.channel_id)}
							<li class="enter" style:--i={i}>
								<a href={channelHref(ch.channel_id)} class="bar-row">
									<span class="bar-label truncate">#{ch.channel_name}</span>
									<span class="bar-track" aria-hidden="true">
										<span class="bar-fill" style:width="{(ch.message_count / most) * 100}%"></span>
									</span>
									<span class="bar-value mono">{ch.message_count.toLocaleString()}</span>
								</a>
							</li>
						{/each}
					</ol>
				{:else}
					<EmptyState icon="hash" title="No channels yet." compact />
				{/if}
			</section>

			<section class="section" aria-labelledby="reactions-title">
				<h2 id="reactions-title" class="section-title"><Icon name="heart" /> Reactions received</h2>
				{#if profile.top_reactions_received.length}
					<p class="section-sub">
						{plural(profile.total_reactions_received, 'reaction', 'reactions')} on their messages
					</p>
					<ul class="reactions">
						{#each profile.top_reactions_received as reaction (reaction.emoji)}
							<li class="reaction" aria-label="{reaction.emoji}: {plural(reaction.count, 'reaction', 'reactions')}">
								<span class="reaction-emoji">{reaction.emoji}</span>
								<span class="reaction-count mono">{reaction.count.toLocaleString()}</span>
							</li>
						{/each}
					</ul>
				{:else}
					<EmptyState icon="heart" title="No reactions yet." compact />
				{/if}
			</section>
		</div>
	{/if}

	{#if !missing && !error}
		<section class="section" aria-labelledby="recent-title">
			<h2 id="recent-title" class="section-title"><Icon name="message" /> Recent messages</h2>
			{#if recentLoading}
				<div class="recent-skeleton" aria-busy="true">
					{#each [0, 1, 2] as i (i)}
						<Skeleton height="56px" radius="sm" />
					{/each}
				</div>
			{:else if recentError}
				<Alert tone="danger" title="The recent messages could not be loaded">{recentError}</Alert>
			{:else if recent.length}
				<ol class="recent">
					{#each recent as { message, channel_name }, i (message.id)}
						<li class="enter" style:--i={i}>
							<a class="recent-row" href={channelHref(message.channel_id, { message: message.id })}>
								<span class="recent-meta">
									<span class="recent-channel">#{channel_name}</span>
									<time class="mono" datetime={message.created_at}>{formatMoment(message.created_at)}</time>
								</span>
								{#if message.content}
									<span class="recent-content">{message.content}</span>
								{:else}
									<span class="recent-content empty">
										{message.attachments.length
											? plural(message.attachments.length, 'attachment', 'attachments')
											: 'No text'}
									</span>
								{/if}
							</a>
						</li>
					{/each}
				</ol>
			{:else}
				<EmptyState icon="inbox" title="No messages in this guild." compact />
			{/if}
		</section>
	{/if}
</div>

<style>
	.profile-page {
		max-width: var(--size-reader-max);
		margin: 0 auto;
		padding: var(--space-8) var(--space-6) var(--space-10);
	}

	/* Breadcrumb */
	.breadcrumb ol {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		list-style: none;
		margin-bottom: var(--space-6);
		font: var(--type-label-sm);
		color: var(--text-tertiary);
		min-width: 0;
	}

	.breadcrumb li {
		display: inline-flex;
		align-items: center;
		min-width: 0;
	}

	.breadcrumb a {
		color: var(--text-secondary);
	}

	.breadcrumb a:hover {
		color: var(--text-primary);
	}

	.breadcrumb [aria-current='page'] {
		color: var(--text-primary);
	}

	/* Hero */
	.hero {
		display: flex;
		align-items: center;
		gap: var(--space-5);
		margin-bottom: var(--space-8);
	}

	.hero-info {
		min-width: 0;
	}

	h1 {
		font: var(--type-display-lg);
		letter-spacing: var(--tracking-display-lg);
		color: var(--text-primary);
		margin-bottom: var(--space-2);
		overflow-wrap: anywhere;
	}

	.hero-meta {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		flex-wrap: wrap;
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.active {
		display: inline-flex;
		align-items: baseline;
		gap: var(--space-1);
		flex-wrap: wrap;
	}

	.active time {
		color: var(--text-primary);
	}

	.profile-skeleton {
		display: flex;
		flex-direction: column;
		gap: var(--space-8);
	}

	.profile-skeleton .hero {
		margin-bottom: 0;
	}

	.skeleton-lines {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	/* Sections */
	.section {
		margin-bottom: var(--space-8);
		min-width: 0;
	}

	.section-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-heading-md);
		color: var(--text-primary);
		margin-bottom: var(--space-3);
	}

	.section-title :global(.icon) {
		color: var(--text-secondary);
	}

	.section-sub {
		font: var(--type-body-sm);
		color: var(--text-secondary);
		margin-bottom: var(--space-3);
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: var(--space-3);
	}

	.columns {
		display: grid;
		grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
		gap: var(--space-6);
	}

	/* Top channels */
	.bars {
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.bar-row {
		display: grid;
		grid-template-columns: minmax(0, 140px) 1fr 56px;
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
		display: block;
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
	.reactions {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.reaction {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		height: 32px;
		padding: 0 var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-full);
	}

	.reaction-emoji {
		font-size: 16px;
		line-height: 1;
	}

	.reaction-count {
		font: var(--type-mono-md);
		color: var(--text-secondary);
	}

	/* Recent messages */
	.recent,
	.recent-skeleton {
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.recent-row {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		background: var(--bg-surface);
		color: inherit;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint);
	}

	.recent-row:hover {
		background: var(--bg-raised);
		border-color: var(--border-default);
		color: inherit;
	}

	.recent-meta {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
		font: var(--type-label-sm);
		color: var(--text-secondary);
	}

	.recent-meta time {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.recent-content {
		font: var(--type-body-md);
		color: var(--text-primary);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		overflow-wrap: anywhere;
	}

	.recent-content.empty {
		color: var(--text-tertiary);
		font-style: italic;
	}

	@media (max-width: 768px) {
		.profile-page {
			padding: var(--space-6) var(--space-4) var(--space-8);
		}

		.hero {
			gap: var(--space-4);
		}

		.stats-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.columns {
			grid-template-columns: minmax(0, 1fr);
			gap: 0;
		}
	}
</style>
