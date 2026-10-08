<!--
	The People screen: the selected guild's authors as a table, ranked in the order
	chosen (most messages, name, or most recently active), searchable by name, 50 rows
	at a time. A row's rank is its place in that order, 1..N however many pages are
	loaded, and its share bar is its part of all the guild's messages.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { getGuildUsers } from '#lib/api.ts';
	import { personHref } from '#lib/routes.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { UserListItem } from '#lib/types.ts';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Avatar from '#lib/components/ui/Avatar.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import IconButton from '#lib/components/ui/IconButton.svelte';
	import SegmentedControl from '#lib/components/ui/SegmentedControl.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';

	type Sort = 'messages' | 'name' | 'recent';

	const SORTS: { value: Sort; label: string }[] = [
		{ value: 'messages', label: 'Messages' },
		{ value: 'name', label: 'Name' },
		{ value: 'recent', label: 'Recently active' }
	];
	const PAGE_SIZE = 50;
	const SEARCH_DELAY_MS = 250;

	const guild = shell.guild;
	let users: UserListItem[] = $state([]);
	let total = $state(0);
	let hasMore = $state(false);
	let loading = $state(true);
	let loadingMore = $state(false);
	let error = $state('');
	let sort: Sort = $state('messages');
	let query = $state('');
	/** The search the rows answer, which the field runs ahead of while it waits. */
	let searched = $state('');

	// Each read is numbered; a reply to anything but the latest is dropped, so a slow
	// page of an earlier sort or search never lands in the table.
	let latest = 0;

	async function load(reset: boolean) {
		if (!guild) return;
		const read = ++latest;
		if (reset) loading = true;
		else loadingMore = true;
		error = '';
		try {
			const res = await getGuildUsers(guild.id, {
				// The next page starts after the authors already listed.
				offset: reset ? 0 : users.length,
				limit: PAGE_SIZE,
				sort,
				q: searched || undefined
			});
			if (read !== latest) return;
			users = reset ? res.users : [...users, ...res.users];
			total = res.total;
			hasMore = res.has_more;
		} catch (e) {
			if (read !== latest) return;
			error = e instanceof Error ? e.message : 'The people could not be loaded';
		} finally {
			if (read === latest) {
				loading = false;
				loadingMore = false;
			}
		}
	}

	onMount(() => {
		if (guild) void load(true);
		else loading = false;
		return () => clearTimeout(searchTimer);
	});

	let searchTimer: ReturnType<typeof setTimeout> | undefined;

	function search(now = false) {
		clearTimeout(searchTimer);
		const run = () => {
			const next = query.trim();
			if (next === searched) return;
			searched = next;
			void load(true);
		};
		if (now) run();
		else searchTimer = setTimeout(run, SEARCH_DELAY_MS);
	}

	function clearSearch() {
		query = '';
		search(true);
	}

	function sortBy(next: Sort) {
		sort = next;
		void load(true);
	}

	const guildMessages = $derived(guild?.message_count ?? 0);

	function share(count: number): number {
		return guildMessages ? count / guildMessages : 0;
	}

	function percent(fraction: number): string {
		const value = fraction * 100;
		return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)}%`;
	}

	function formatDay(iso: string, withYear: boolean): string {
		return new Date(iso).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			...(withYear ? { year: 'numeric' } : {})
		});
	}

	function sameYear(a: string, b: string): boolean {
		return new Date(a).getFullYear() === new Date(b).getFullYear();
	}

	/** Which column the rows are ordered by, for aria-sort. */
	const SORTED_COLUMN: Record<Sort, string> = { messages: 'messages', name: 'person', recent: 'active' };
	function ariaSort(column: string): 'ascending' | 'descending' | undefined {
		if (SORTED_COLUMN[sort] !== column) return undefined;
		return sort === 'name' ? 'ascending' : 'descending';
	}
</script>

<div class="people-page">
	<header class="page-header">
		<h1>People</h1>
		<p class="summary">
			{#if !guild}
				No guild is archived yet.
			{:else if loading && !users.length}
				Counting the people in <strong>{guild.name}</strong>…
			{:else if searched}
				<span class="mono">{total.toLocaleString()}</span>
				{total === 1 ? 'person matches' : 'people match'} “{searched}” in <strong>{guild.name}</strong>
			{:else}
				<span class="mono">{total.toLocaleString()}</span>
				{total === 1 ? 'person has' : 'people have'} posted in <strong>{guild.name}</strong>
			{/if}
		</p>

		<div class="controls">
			<form
				class="search"
				role="search"
				onsubmit={(event) => {
					event.preventDefault();
					search(true);
				}}
			>
				<Icon name="search" size={16} />
				<input
					type="search"
					bind:value={query}
					oninput={() => search()}
					placeholder="Search by name"
					aria-label="Search people by name"
					autocomplete="off"
					spellcheck="false"
				/>
				{#if query}
					<IconButton icon="x" label="Clear search" size="sm" onclick={clearSearch} />
				{/if}
			</form>

			<SegmentedControl label="Sort by" options={SORTS} value={sort} onchange={sortBy} />
		</div>
	</header>

	{#if error}
		<Alert tone="danger" title="The people could not be loaded">{error}</Alert>
	{:else if !loading && users.length === 0}
		{#if searched}
			<EmptyState icon="search-x" title="No one matches “{searched}”." description="Search matches a person's name or handle." />
		{:else}
			<EmptyState icon="users" title="No one has posted in this guild yet." />
		{/if}
	{:else}
		<table class="people-table" class:stale={loading && users.length > 0} aria-busy={loading}>
			<caption class="sr-only">
				People in {guild?.name}, ranked by {SORTS.find((s) => s.value === sort)?.label.toLowerCase()}
			</caption>
			<thead>
				<tr>
					<th scope="col" class="rank-col"><span class="sr-only">Rank</span><span aria-hidden="true">#</span></th>
					<th scope="col" class="person-col" aria-sort={ariaSort('person')}>Person</th>
					<th scope="col" class="share-col">Share of messages</th>
					<th scope="col" class="count-col" aria-sort={ariaSort('messages')}>Messages</th>
					<th scope="col" class="active-col" aria-sort={ariaSort('active')}>Active</th>
				</tr>
			</thead>
			<tbody>
				{#if loading && !users.length}
					{#each Array.from({ length: 8 }, (_, i) => i) as i (i)}
						<tr class="skeleton-row">
							<td class="rank-col"><Skeleton width="20px" height="12px" /></td>
							<td class="person-col">
								<span class="person">
									<Skeleton width="32px" height="32px" radius="full" />
									<Skeleton width="140px" height="14px" />
								</span>
							</td>
							<td class="share-col"><Skeleton height="6px" radius="full" /></td>
							<td class="count-col"><Skeleton width="40px" height="14px" /></td>
							<td class="active-col"><Skeleton width="150px" height="12px" /></td>
						</tr>
					{/each}
				{:else}
					{#each users as user, i (user.id)}
						{@const name = user.display_name || user.username}
						{@const fraction = share(user.message_count)}
						<tr class="person-row" class:enter={i < PAGE_SIZE} style:--i={i}>
							<td class="rank-col mono">{i + 1}</td>
							<td class="person-col">
								<a class="person" href={personHref(user.id)}>
									<Avatar src={user.avatar_url} {name} size={32} />
									<span class="names">
										<span class="name truncate">{name}</span>
										{#if user.username !== name}
											<span class="handle mono truncate">@{user.username}</span>
										{/if}
									</span>
									{#if user.bot}<Badge tone="accent">BOT</Badge>{/if}
								</a>
							</td>
							<td class="share-col">
								<span class="share">
									<span class="track" aria-hidden="true">
										<span class="fill" style:width="{Math.min(100, fraction * 100)}%"></span>
									</span>
									<span class="pct mono">{percent(fraction)}</span>
								</span>
							</td>
							<td class="count-col mono">{user.message_count.toLocaleString()}</td>
							<td class="active-col mono">
								{#if user.first_seen && user.last_seen}
									{@const withYear = !sameYear(user.first_seen, user.last_seen)}
									<time datetime={user.first_seen}>{formatDay(user.first_seen, withYear)}</time>
									–
									<time datetime={user.last_seen}>{formatDay(user.last_seen, true)}</time>
								{:else}
									<span aria-label="Unknown">—</span>
								{/if}
							</td>
						</tr>
					{/each}
				{/if}
			</tbody>
		</table>

		{#if hasMore && !loading}
			<LoadMore loading={loadingMore} onclick={() => load(false)}>
				Load more ({(total - users.length).toLocaleString()} remaining)
			</LoadMore>
		{/if}
	{/if}
</div>

<style>
	.people-page {
		max-width: 1040px;
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

	.summary {
		font: var(--type-body-md);
		color: var(--text-secondary);
		margin-bottom: var(--space-5);
	}

	.summary strong {
		color: var(--text-primary);
		font-weight: 600;
	}

	.controls {
		display: flex;
		gap: var(--space-3);
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
	}

	.search {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex: 1;
		min-width: 200px;
		max-width: 360px;
		height: 34px;
		padding: 0 var(--space-1) 0 var(--space-3);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		background: var(--bg-surface);
		color: var(--text-tertiary);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.search:focus-within {
		border-color: var(--border-strong);
	}

	.search input {
		flex: 1;
		min-width: 0;
		height: 100%;
		border: none;
		outline: none;
		background: transparent;
		color: var(--text-primary);
		font: var(--type-body-md);
	}

	.search input::placeholder {
		color: var(--text-tertiary);
	}

	.search input::-webkit-search-cancel-button {
		display: none;
	}

	/* The table */
	.people-table {
		width: 100%;
		border-collapse: collapse;
		table-layout: fixed;
	}

	th {
		padding: var(--space-2) var(--space-3);
		border-bottom: 1px solid var(--border-subtle);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
		text-align: left;
		white-space: nowrap;
	}

	th[aria-sort] {
		color: var(--text-secondary);
	}

	td {
		padding: var(--space-2) var(--space-3);
		border-bottom: 1px solid var(--border-subtle);
		vertical-align: middle;
		color: var(--text-secondary);
	}

	.rank-col {
		width: 56px;
		text-align: right;
	}

	td.rank-col {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.share-col {
		width: 200px;
	}

	.count-col {
		width: 104px;
		text-align: right;
	}

	td.count-col {
		font: var(--type-mono-md);
		font-weight: 500;
		color: var(--text-primary);
	}

	.active-col {
		width: 220px;
	}

	td.active-col {
		font: var(--type-mono-sm);
		white-space: nowrap;
	}

	/* A whole row opens the person: their link covers it. */
	.person-row {
		position: relative;
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.person-row:hover {
		background: var(--bg-hover);
	}

	.person {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		min-width: 0;
		color: inherit;
	}

	.person:hover {
		color: inherit;
	}

	a.person::after {
		content: '';
		position: absolute;
		inset: 0;
	}

	a.person:focus-visible {
		outline: none;
	}

	.person-row:has(a.person:focus-visible) {
		outline: 2px solid var(--accent-glow);
		outline-offset: -2px;
	}

	.names {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.name {
		font: var(--type-label-md);
		color: var(--text-primary);
	}

	.handle {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.share {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.track {
		flex: 1;
		height: 6px;
		background: var(--bg-raised);
		border-radius: var(--radius-full);
		overflow: hidden;
	}

	.fill {
		display: block;
		height: 100%;
		min-width: 2px;
		background: var(--accent);
		border-radius: var(--radius-full);
	}

	.pct {
		width: 44px;
		text-align: right;
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	/* The rows of the last order or search, while the next loads. */
	.stale tbody {
		opacity: 0.5;
		transition: opacity var(--duration-small) var(--ease-standard);
	}

	.skeleton-row td {
		height: 53px;
	}

	@media (max-width: 900px) {
		.share-col {
			width: 140px;
		}

		.active-col {
			display: none;
		}
	}

	@media (max-width: 600px) {
		.people-page {
			padding: var(--space-6) var(--space-4);
		}

		.rank-col {
			width: 36px;
		}

		.share-col {
			display: none;
		}

		.count-col {
			width: 72px;
		}
	}
</style>
