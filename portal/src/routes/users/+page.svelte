<script lang="ts">
	import { onMount } from 'svelte';
	import { getGuildUsers } from '#lib/api.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { UserListItem } from '#lib/types.ts';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import SearchBar from '#lib/components/SearchBar.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import Chip from '#lib/components/ui/Chip.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	const guild = shell.guild;
	let users: UserListItem[] = $state([]);
	let total = $state(0);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let searchQuery = $state('');
	let sortBy = $state('messages');
	let hasMore = $state(false);
	const PAGE_SIZE = 50;

	async function loadUsers(reset = false) {
		if (!guild) return;
		if (reset) {
			users = [];
			loading = true;
		} else {
			loadingMore = true;
		}

		try {
			const res = await getGuildUsers(guild.id, {
				// The next page starts after the authors already listed.
				offset: users.length,
				limit: PAGE_SIZE,
				sort: sortBy,
				q: searchQuery || undefined,
			});
			if (reset) {
				users = res.users;
			} else {
				users = [...users, ...res.users];
			}
			total = res.total;
			hasMore = res.has_more;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load users';
		} finally {
			loading = false;
			loadingMore = false;
		}
	}

	onMount(async () => {
		if (guild) await loadUsers(true);
		else loading = false;
	});

	function handleSearch(query: string) {
		searchQuery = query;
		loadUsers(true);
	}

	function handleSort(newSort: string) {
		sortBy = newSort;
		loadUsers(true);
	}

	function loadMore() {
		loadUsers(false);
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
		});
	}

	function getMaxCount(): number {
		if (!users.length) return 1;
		return Math.max(users[0]?.message_count ?? 1, 1);
	}
</script>

<div class="users-page">
	<header class="page-header">
		<h1>People</h1>
		<p class="header-sub">
			{#if guild}
				<span class="mono">{total.toLocaleString()}</span> contributors in <strong>{guild.name}</strong>
			{:else}
				Loading...
			{/if}
		</p>

		<div class="controls">
			<div class="search-wrap">
				<SearchBar
					bind:value={searchQuery}
					placeholder="Search users..."
					label="Search users"
					onsubmit={handleSearch}
				/>
			</div>

			<div class="sort-group" role="group" aria-label="Sort by">
				<Chip selected={sortBy === 'messages'} onclick={() => handleSort('messages')}>Most Active</Chip>
				<Chip selected={sortBy === 'recent'} onclick={() => handleSort('recent')}>Recent</Chip>
				<Chip selected={sortBy === 'name'} onclick={() => handleSort('name')}>A–Z</Chip>
			</div>
		</div>
	</header>

	{#if loading}
		<div class="user-list" aria-busy="true">
			<span class="sr-only" role="status">Loading users…</span>
			{#each Array.from({ length: 8 }, (_, i) => i) as i (i)}
				<div class="user-row skeleton-row">
					<div class="user-identity">
						<Skeleton width="28px" height="12px" />
						<Skeleton width="36px" height="36px" radius="full" />
						<Skeleton width="140px" height="14px" />
					</div>
					<Skeleton height="6px" radius="full" />
					<div class="user-meta"><Skeleton width="64px" height="14px" /></div>
				</div>
			{/each}
		</div>
	{:else if error}
		<Alert tone="danger" title="The users could not be loaded">{error}</Alert>
	{:else if users.length === 0}
		<EmptyState icon="users" title="No users found." />
	{:else}
		<div class="user-list">
			{#each users as user, i (user.id)}
				{@const pct = (user.message_count / getMaxCount()) * 100}
				<a
					class="user-row"
					class:enter={i < PAGE_SIZE}
					href="/users/{user.id}"
					style:--i={i}
				>
					<div class="user-identity">
						<span class="user-rank mono">#{i + 1}</span>
						{#if user.avatar_url}
							<img
								class="user-avatar"
								src={user.avatar_url}
								alt={user.display_name || user.username}
								loading="lazy"
							/>
						{:else}
							<div class="user-avatar avatar-fallback">
								{(user.username || '?')[0].toUpperCase()}
							</div>
						{/if}
						<div class="user-names">
							<span class="user-display">{user.display_name || user.username}</span>
							{#if user.global_name && user.global_name !== user.username}
								<span class="user-handle mono">@{user.username}</span>
							{/if}
							{#if user.bot}
								<Badge tone="accent">BOT</Badge>
							{/if}
						</div>
					</div>

					<div class="user-stats">
						<div class="stat-bar-bg">
							<div class="stat-bar-fill" style="width: {pct}%"></div>
						</div>
					</div>

					<div class="user-meta">
						<span class="user-count mono">{user.message_count.toLocaleString()}</span>
						<span class="user-dates mono">
							{formatDate(user.first_seen)} — {formatDate(user.last_seen)}
						</span>
					</div>
				</a>
			{/each}
		</div>

		{#if hasMore}
			<LoadMore loading={loadingMore} onclick={loadMore}>
				Load more ({total - users.length} remaining)
			</LoadMore>
		{/if}
	{/if}
</div>

<style>
	.users-page {
		max-width: var(--size-reader-max);
		margin: 0 auto;
		padding: var(--space-10) var(--space-6);
	}

	.page-header {
		margin-bottom: var(--space-6);
	}

	h1 {
		font: var(--type-display-lg);
		letter-spacing: var(--tracking-display-lg);
		color: var(--text-primary);
		margin-bottom: var(--space-2);
	}

	.header-sub {
		font: var(--type-body-md);
		color: var(--text-secondary);
		margin-bottom: var(--space-5);
	}

	.header-sub strong {
		color: var(--text-primary);
		font-weight: 600;
	}

	.controls {
		display: flex;
		gap: var(--space-4);
		align-items: center;
		flex-wrap: wrap;
	}

	.search-wrap {
		flex: 1;
		min-width: 200px;
		max-width: 360px;
	}

	.sort-group {
		display: flex;
		gap: var(--space-1);
	}

	.user-list {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.user-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 160px 200px;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-sm);
		color: inherit;
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.user-row:hover {
		background: var(--bg-hover);
		color: inherit;
	}

	.skeleton-row:hover {
		background: none;
	}

	.user-identity {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		min-width: 0;
	}

	.user-rank {
		width: 36px;
		text-align: center;
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		flex-shrink: 0;
	}

	.user-avatar {
		width: 36px;
		height: 36px;
		border-radius: var(--radius-full);
		object-fit: cover;
		flex-shrink: 0;
	}

	.avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-secondary);
		font: var(--type-label-md);
	}

	.user-names {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
	}

	.user-display {
		font: var(--type-label-md);
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.user-handle {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	.user-stats {
		display: flex;
		align-items: center;
	}

	.stat-bar-bg {
		width: 100%;
		height: 6px;
		background: var(--bg-raised);
		border-radius: var(--radius-full);
		overflow: hidden;
	}

	.stat-bar-fill {
		height: 100%;
		background: var(--accent);
		border-radius: var(--radius-full);
	}

	.user-meta {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 2px;
	}

	.user-count {
		font: var(--type-mono-md);
		font-weight: 500;
		color: var(--text-primary);
	}

	.user-dates {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	@media (max-width: 768px) {
		.user-row {
			grid-template-columns: 1fr 80px;
		}

		.user-stats {
			display: none;
		}

		.user-dates {
			display: none;
		}
	}
</style>
