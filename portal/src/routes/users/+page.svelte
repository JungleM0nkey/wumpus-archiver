<script lang="ts">
	import { onMount } from 'svelte';
	import { getGuilds, getGuildUsers } from '$lib/api';
	import type { Guild, UserListItem } from '$lib/types';
	import SearchBar from '$lib/components/SearchBar.svelte';

	let guild: Guild | null = $state(null);
	let users: UserListItem[] = $state([]);
	let total = $state(0);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let searchQuery = $state('');
	let sortBy = $state('messages');
	let offset = $state(0);
	let hasMore = $state(false);
	const PAGE_SIZE = 50;

	async function loadUsers(reset = false) {
		if (!guild) return;
		if (reset) {
			offset = 0;
			users = [];
			loading = true;
		} else {
			loadingMore = true;
		}

		try {
			const res = await getGuildUsers(guild.id, {
				offset,
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
		offset += PAGE_SIZE;
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
				<h1 class="serif">Users<span class="dot">.</span></h1>
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
					class="user-row fade-in"
					href="/users/{user.id}"
					style="animation-delay: {Math.min(i, 20) * 25}ms"
				>
					<div class="user-identity">
						<span class="user-rank mono">#{i + 1 + offset - users.length + users.length}</span>
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
		max-width: var(--max-content);
		margin: 0 auto;
		padding: var(--sp-8) var(--sp-6);
	}

	.page-header {
		margin-bottom: var(--sp-8);
	}

	.header-top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: var(--sp-5);
	}

	h1 {
		font-size: 36px;
		font-weight: 700;
		letter-spacing: -0.04em;
		line-height: 1;
		margin-bottom: var(--sp-2);
		color: var(--text-primary);
	}

	.dot { color: var(--accent); }

	.header-sub {
		font-size: 15px;
		color: var(--text-secondary);
	}

	.controls {
		display: flex;
		gap: var(--sp-4);
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
		gap: var(--sp-1);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		padding: 3px;
	}

	.sort-btn {
		padding: var(--sp-1) var(--sp-3);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-muted);
		border-radius: var(--radius-sm);
		transition: all 0.15s var(--ease-out);
	}

	.sort-btn:hover {
		color: var(--text-secondary);
		background: var(--bg-hover);
	}

	.sort-btn.active {
		color: var(--accent-text);
		background: var(--accent-glow);
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
		gap: var(--sp-4);
		padding: var(--sp-3) var(--sp-4);
		border-radius: var(--radius-md);
		text-decoration: none;
		color: inherit;
		transition: background 0.15s var(--ease-out);
	}

	.user-row:hover {
		background: var(--bg-hover);
		text-decoration: none;
	}

	.user-identity {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		min-width: 0;
	}

	.user-rank {
		width: 36px;
		text-align: center;
		font-size: 12px;
		color: var(--text-faint);
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
		color: var(--text-muted);
		font-weight: 600;
		font-size: 14px;
	}

	.user-names {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
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
		color: var(--text-muted);
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
		background: linear-gradient(90deg, var(--accent-dim), var(--accent));
		border-radius: 3px;
		transition: width 0.5s var(--ease-out);
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
		color: var(--text-muted);
		white-space: nowrap;
	}

	.load-more {
		display: flex;
		justify-content: center;
		padding: var(--sp-8) 0;
	}

	.load-more-btn {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-2) var(--sp-6);
		font-size: 14px;
		font-weight: 500;
		color: var(--accent-text);
		background: var(--accent-glow);
		border: 1px solid var(--border-accent);
		border-radius: var(--radius-md);
		transition: all 0.15s var(--ease-out);
	}

	.load-more-btn:hover:not(:disabled) {
		background: var(--accent);
		color: var(--bg-base);
	}

	.load-more-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

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
