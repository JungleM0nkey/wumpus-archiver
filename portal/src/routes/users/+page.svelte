<script lang="ts">
	import { onMount } from 'svelte';
	import { getGuilds, getGuildUsers } from '#lib/api.ts';
	import type { Guild, UserListItem } from '#lib/types.ts';
	import SearchBar from '#lib/components/SearchBar.svelte';

	let guild: Guild | null = $state(null);
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
		try {
			const guilds = await getGuilds();
			if (guilds.length > 0) {
				guild = guilds[0];
				await loadUsers(true);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load data';
			loading = false;
		}
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
		<div class="header-top">
			<div>
				<h1>Users</h1>
				<p class="header-sub">
					{#if guild}
						{total.toLocaleString()} contributors in <strong>{guild.name}</strong>
					{:else}
						Loading...
					{/if}
				</p>
			</div>
		</div>

		<div class="controls">
			<div class="search-wrap">
				<SearchBar
					bind:value={searchQuery}
					placeholder="Search users..."
					onsubmit={handleSearch}
				/>
			</div>

			<div class="sort-group">
				<button
					class="sort-btn"
					class:active={sortBy === 'messages'}
					onclick={() => handleSort('messages')}
				>
					Most Active
				</button>
				<button
					class="sort-btn"
					class:active={sortBy === 'recent'}
					onclick={() => handleSort('recent')}
				>
					Recent
				</button>
				<button
					class="sort-btn"
					class:active={sortBy === 'name'}
					onclick={() => handleSort('name')}
				>
					A–Z
				</button>
			</div>
		</div>
	</header>

	{#if loading}
		<div class="center-state">
			<div class="spinner"></div>
			<span class="mono">Loading users...</span>
		</div>
	{:else if error}
		<div class="center-state error">⚠ {error}</div>
	{:else if users.length === 0}
		<div class="center-state">No users found.</div>
	{:else}
		<div class="user-list">
			{#each users as user, i (user.id)}
				{@const pct = (user.message_count / getMaxCount()) * 100}
				<a
					class="user-row enter"
					href="/users/{user.id}"
					style="--i: {i}"
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
								<span class="badge accent">BOT</span>
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
			<div class="load-more">
				<button class="load-more-btn" onclick={loadMore} disabled={loadingMore}>
					{#if loadingMore}
						<div class="spinner small"></div>
						Loading...
					{:else}
						Load more ({total - users.length} remaining)
					{/if}
				</button>
			</div>
		{/if}
	{/if}
</div>

<style>
	.users-page {
		max-width: var(--size-reader-max);
		margin: 0 auto;
		padding: var(--space-8) var(--space-6);
	}

	.page-header {
		margin-bottom: var(--space-8);
	}

	.header-top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: var(--space-5);
	}

	h1 {
		font-size: 36px;
		font-weight: 700;
		letter-spacing: -0.04em;
		line-height: 1;
		margin-bottom: var(--space-2);
		color: var(--text-primary);
	}


	.header-sub {
		font-size: 15px;
		color: var(--text-secondary);
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
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		padding: 3px;
	}

	.sort-btn {
		padding: var(--space-1) var(--space-3);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-tertiary);
		border-radius: var(--radius-xs);
		transition: all var(--duration-micro) var(--ease-out-quint);
	}

	.sort-btn:hover {
		color: var(--text-secondary);
		background: var(--bg-hover);
	}

	.sort-btn.active {
		color: var(--accent);
		background: var(--accent-muted);
	}

	.user-list {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.user-row {
		display: grid;
		grid-template-columns: 1fr 200px 160px;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-3) var(--space-4);
		border-radius: var(--radius-sm);
		text-decoration: none;
		color: inherit;
		transition: background var(--duration-micro) var(--ease-out-quint);
	}

	.user-row:hover {
		background: var(--bg-hover);
		text-decoration: none;
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
		font-size: 12px;
		color: var(--text-tertiary);
		flex-shrink: 0;
	}

	.user-avatar {
		width: 36px;
		height: 36px;
		border-radius: 50%;
		object-fit: cover;
		flex-shrink: 0;
	}

	.avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-overlay);
		color: var(--text-tertiary);
		font-weight: 600;
		font-size: 14px;
	}

	.user-names {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
	}

	.user-display {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.user-handle {
		font-size: 12px;
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
		border-radius: 3px;
		overflow: hidden;
	}

	.stat-bar-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--accent-strong), var(--accent));
		border-radius: 3px;
		transition: width var(--duration-large) var(--ease-out-quint);
	}

	.user-meta {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 2px;
	}

	.user-count {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.user-dates {
		font-size: 11px;
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	.load-more {
		display: flex;
		justify-content: center;
		padding: var(--space-8) 0;
	}

	.load-more-btn {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-6);
		font-size: 14px;
		font-weight: 500;
		color: var(--accent);
		background: var(--accent-muted);
		border: 1px solid var(--accent-glow);
		border-radius: var(--radius-sm);
		transition: all var(--duration-micro) var(--ease-out-quint);
	}

	.load-more-btn:hover:not(:disabled) {
		background: var(--accent);
		color: var(--bg-canvas);
	}

	.load-more-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

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
