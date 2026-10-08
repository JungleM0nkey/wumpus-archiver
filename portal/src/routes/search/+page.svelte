<!--
	Search (#64): the selected guild's messages that hold every search term, narrowed by
	filter chips written into the query (`in:`, `from:`, `has:`, `after:`, `before:`, see
	lib/search.ts). The whole query is the URL's `q` and the order its `sort`, so reload,
	back and forward and the sidebar's search field all go through the URL. Results show
	the highlighted snippet with "Open in context" into Browse; the refine rail counts
	them per channel, person and month, and each count adds its chip.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { getGuild, getGuildUsers, searchMessages } from '#lib/api.ts';
	import { isReadable } from '#lib/channels.ts';
	import { channelHref, personHref } from '#lib/routes.ts';
	import {
		chipValue,
		formatQuery,
		isEmpty,
		parseQuery,
		snippetRuns,
		withChip,
		withoutChips,
		type Chip,
		type HasKind,
		type SearchQuery
	} from '#lib/search.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { Channel, SearchFacets, SearchResult } from '#lib/types.ts';
	import LoadMore from '#lib/components/LoadMore.svelte';
	import MessageSkeleton from '#lib/components/MessageSkeleton.svelte';
	import SearchQueryBar, { type Suggestion } from '#lib/components/search/SearchQueryBar.svelte';
	import SearchRefine from '#lib/components/search/SearchRefine.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Avatar from '#lib/components/ui/Avatar.svelte';
	import Button from '#lib/components/ui/Button.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import SegmentedControl from '#lib/components/ui/SegmentedControl.svelte';

	type Sort = 'newest' | 'oldest';
	const PAGE_SIZE = 50;
	const SORTS: { value: Sort; label: string }[] = [
		{ value: 'newest', label: 'Newest' },
		{ value: 'oldest', label: 'Oldest' }
	];

	const guild = shell.guild;

	// The guild's channels, which `in:` names and suggests; read once.
	let channels: Channel[] = [];
	const channelsRead: Promise<void> = guild
		? getGuild(guild.id).then(
				(detail) => void (channels = detail.channels.filter(isReadable)),
				(e) => console.error('Failed to load channels:', e)
			)
		: Promise.resolve();
	let channelNames: string[] = $state([]);
	void channelsRead.then(() => (channelNames = channels.map((c) => c.name)));

	/** Authors by lowercased username, as facets and suggestions named them. */
	const authorsByName = new Map<string, { id: string; display_name: string }>();

	// What the URL asks for. `key` changes only when the query or the sort does.
	const key = $derived(`${page.url.searchParams.get('sort') === 'oldest' ? 'oldest' : 'newest'}\n${page.url.searchParams.get('q') ?? ''}`);
	const query: SearchQuery = $derived(parseQuery(page.url.searchParams.get('q') ?? ''));
	const sort: Sort = $derived(page.url.searchParams.get('sort') === 'oldest' ? 'oldest' : 'newest');

	let draft = $state('');
	let input: HTMLInputElement | undefined = $state();

	type Status = 'idle' | 'loading' | 'done' | 'error' | 'unresolved';
	let status: Status = $state('idle');
	let problem = $state('');
	let results: SearchResult[] = $state([]);
	let total = $state(0);
	let hasMore = $state(false);
	let facets: SearchFacets | null = $state(null);
	let loadingMore = $state(false);
	let refineOpen = $state(false);

	/** The filters the API was last asked with, for the next page. */
	let asked: Parameters<typeof searchMessages> | null = null;
	let runs = 0;

	$effect(() => {
		void key;
		untrack(() => void run(query, sort));
	});

	async function resolveAuthor(name: string): Promise<string | null> {
		const known = authorsByName.get(name.toLowerCase());
		if (known) return known.id;
		if (!guild) return null;
		const found = await getGuildUsers(guild.id, { q: name, limit: 25 });
		const lower = name.toLowerCase();
		const user =
			found.users.find((u) => u.username.toLowerCase() === lower) ??
			found.users.find((u) => (u.display_name ?? u.global_name ?? '').toLowerCase() === lower);
		if (!user) return null;
		authorsByName.set(lower, { id: user.id, display_name: user.display_name ?? user.username });
		return user.id;
	}

	async function run(next: SearchQuery, order: Sort) {
		const ticket = ++runs;
		draft = next.text;
		results = [];
		facets = null;
		hasMore = false;
		problem = '';
		asked = null;
		if (isEmpty(next)) {
			status = 'idle';
			return;
		}
		status = 'loading';
		try {
			await channelsRead;
			const inName = chipValue(next, 'in');
			const channel = inName
				? channels.find((c) => c.name.toLowerCase() === inName.toLowerCase())
				: undefined;
			const fromName = chipValue(next, 'from');
			const authorId = fromName ? await resolveAuthor(fromName) : undefined;
			if (ticket !== runs) return;
			if (inName && !channel) {
				status = 'unresolved';
				problem = `No channel is named #${inName} in ${guild?.name ?? 'this guild'}.`;
				return;
			}
			if (fromName && !authorId) {
				status = 'unresolved';
				problem = `Nobody named ${fromName} has posted in ${guild?.name ?? 'this guild'}.`;
				return;
			}
			asked = [
				next.text,
				{
					guild_id: guild?.id,
					channel_id: channel?.id,
					author_id: authorId ?? undefined,
					has: chipValue(next, 'has') as HasKind | undefined,
					after: chipValue(next, 'after'),
					before: chipValue(next, 'before'),
					sort: order,
					limit: PAGE_SIZE
				}
			];
			const res = await searchMessages(asked[0], { ...asked[1], facets: true });
			if (ticket !== runs) return;
			results = res.results;
			total = res.total;
			hasMore = res.has_more;
			facets = res.facets;
			for (const author of res.facets?.authors ?? []) {
				authorsByName.set(author.username.toLowerCase(), author);
			}
			status = 'done';
		} catch (e) {
			if (ticket !== runs) return;
			status = 'error';
			problem = e instanceof Error ? e.message : 'Search failed';
		}
	}

	async function loadMore() {
		if (!asked || !results.length) return;
		const ticket = runs;
		loadingMore = true;
		try {
			const res = await searchMessages(asked[0], {
				...asked[1],
				cursor: results[results.length - 1].message.id
			});
			if (ticket !== runs) return;
			results = [...results, ...res.results];
			hasMore = res.has_more;
		} catch (e) {
			if (ticket === runs) problem = e instanceof Error ? e.message : 'Loading more failed';
		} finally {
			loadingMore = false;
		}
	}

	/** Go to the URL for `next` and `order`: a new history entry, the field kept focused. */
	function show(next: SearchQuery, order: Sort = sort) {
		const url = new URL(page.url.href);
		const q = formatQuery(next);
		if (q) url.searchParams.set('q', q);
		else url.searchParams.delete('q');
		if (order === 'oldest') url.searchParams.set('sort', 'oldest');
		else url.searchParams.delete('sort');
		void goto(url.pathname + url.search, { reset: false });
	}

	function submit(text: string, picked?: Chip) {
		const typed = parseQuery(text);
		const chips = picked ? [...typed.chips, picked] : typed.chips;
		if (picked?.kind === 'from') {
			const known = suggested.get(picked.value.toLowerCase());
			if (known) authorsByName.set(picked.value.toLowerCase(), known);
		}
		show(withChip({ text: typed.text, chips: query.chips }, ...chips));
	}

	function remove(chip: Chip) {
		show(withoutChips({ text: draft, chips: query.chips }, chip.kind));
		input?.focus();
	}

	function clear() {
		draft = '';
		show({ text: '', chips: [] });
		input?.focus();
	}

	/** Add `chips` to the query, or take them off when the refine rail shows them in force. */
	function toggle(chips: Chip[]) {
		const on = chips.every(
			(chip) => chipValue(query, chip.kind)?.toLowerCase() === chip.value.toLowerCase()
		);
		const kinds = chips.map((chip) => chip.kind);
		show(on ? withoutChips(query, ...kinds) : withChip(query, ...chips));
	}

	/** Authors the `from:` suggestions offered, by lowercased username. */
	const suggested = new Map<string, { id: string; display_name: string }>();

	async function findAuthors(partial: string): Promise<Suggestion[]> {
		if (!guild) return [];
		try {
			const found = await getGuildUsers(guild.id, { q: partial || undefined, limit: 6 });
			return found.users.map((user) => {
				const name = user.display_name ?? user.username;
				suggested.set(user.username.toLowerCase(), { id: user.id, display_name: name });
				return {
					chip: { kind: 'from', value: user.username },
					label: name,
					detail: `${user.message_count.toLocaleString()} msgs`,
					avatar: user.avatar_url
				};
			});
		} catch {
			return [];
		}
	}

	const TIME = new Intl.DateTimeFormat('en-US', {
		month: 'short',
		day: 'numeric',
		year: 'numeric',
		hour: 'numeric',
		minute: '2-digit'
	});

	function attachmentSummary(result: SearchResult): string {
		const attachments = result.message.attachments;
		const images = attachments.filter((a) => a.content_type?.startsWith('image/')).length;
		const videos = attachments.filter((a) => a.content_type?.startsWith('video/')).length;
		const files = attachments.length - images - videos;
		const count = (n: number, one: string) => (n ? [`${n} ${one}${n === 1 ? '' : 's'}`] : []);
		return [...count(images, 'image'), ...count(videos, 'video'), ...count(files, 'file')].join(' · ');
	}
</script>

<div class="search-page">
	<header class="search-header">
		<h1>Search</h1>
		<p class="summary">
			Find messages in <strong>{guild?.name ?? 'the archive'}</strong>. Narrow them with
			<code>in:</code>, <code>from:</code>, <code>has:</code>, <code>after:</code> and <code>before:</code>.
		</p>
		<SearchQueryBar
			chips={query.chips}
			bind:draft
			bind:input
			channels={channelNames}
			{findAuthors}
			onsubmit={submit}
			onremove={remove}
			onclear={clear}
		/>
		{#if status === 'done'}
			<div class="result-bar">
				<p class="result-count" aria-live="polite">
					<span class="mono">{total.toLocaleString()}</span>
					{total === 1 ? 'result' : 'results'}
				</p>
				<div class="result-actions">
					{#if facets}
						<span class="refine-toggle">
							<Button
								variant="ghost"
								size="sm"
								icon="refine"
								aria-expanded={refineOpen}
								aria-controls="search-refine"
								onclick={() => (refineOpen = !refineOpen)}>Refine</Button
							>
						</span>
					{/if}
					<SegmentedControl
						options={SORTS}
						value={sort}
						label="Sort results"
						onchange={(order) => show(query, order)}
					/>
				</div>
			</div>
		{/if}
	</header>

	<div class="search-body" class:with-rail={status === 'done' && facets && total > 0}>
		<div class="results-column">
			{#if status === 'loading'}
				<MessageSkeleton count={3} label="Searching…" />
			{:else if status === 'error'}
				<Alert tone="danger" title="The search failed">{problem}</Alert>
			{:else if status === 'unresolved'}
				<EmptyState icon="search-x" title="That filter matches nothing" description={problem}>
					<Button variant="secondary" size="sm" icon="x" onclick={clear}>Clear search</Button>
				</EmptyState>
			{:else if status === 'idle'}
				<EmptyState
					icon="search"
					title="Search the archive"
					description="Type words to find, or a filter such as from:alice, in:general, has:image or after:2024-01-01."
				/>
			{:else if results.length === 0}
				<EmptyState
					icon="search-x"
					title="No messages match"
					description={query.chips.length
						? 'Try other words, or remove a filter.'
						: 'Try other words, or fewer of them.'}
				>
					{#if query.chips.length}
						<Button variant="secondary" size="sm" icon="x" onclick={() => show({ text: query.text, chips: [] })}>
							Remove filters
						</Button>
					{/if}
				</EmptyState>
			{:else}
				<ol class="results" aria-label="Results">
					{#each results as result, i (result.message.id)}
						{@const message = result.message}
						{@const name = message.author?.display_name || message.author?.username || 'Unknown'}
						{@const summary = attachmentSummary(result)}
						<li class="result enter" style:--i={Math.min(i, 8)}>
							<div class="result-meta">
								<Avatar src={message.author?.avatar_url} {name} size={20} />
								{#if message.author}
									<a class="author" href={personHref(message.author.id)}>{name}</a>
								{:else}
									<span class="author">{name}</span>
								{/if}
								<span class="in">in</span>
								<a class="channel" href={channelHref(message.channel_id)}>
									<Icon name="hash" size={14} />{result.channel_name}
								</a>
								<time class="mono" datetime={message.created_at}>
									{TIME.format(new Date(message.created_at))}
								</time>
							</div>
							{#if result.highlight}
								<!-- The API's escaped snippet, rendered as text runs: no markup is set from it. -->
								<p class="snippet">
									{#each snippetRuns(result.highlight) as piece, r (r)}{#if piece.mark}<mark>{piece.text}</mark>{:else}{piece.text}{/if}{/each}
								</p>
							{/if}
							{#if summary}
								<p class="attachments"><Icon name="paperclip" size={14} />{summary}</p>
							{/if}
							<a class="open-context" href={channelHref(message.channel_id, { message: message.id })}>
								Open in context <Icon name="arrow-up-right" size={14} />
							</a>
						</li>
					{/each}
				</ol>
				{#if problem}
					<Alert tone="danger" title="Loading more failed">{problem}</Alert>
				{/if}
				{#if hasMore}
					<LoadMore loading={loadingMore} onclick={loadMore}>Load more results</LoadMore>
				{/if}
			{/if}
		</div>

		{#if status === 'done' && facets && total > 0}
			<aside id="search-refine" class="refine-rail" class:expanded={refineOpen} aria-label="Refine">
				<SearchRefine {facets} {query} ontoggle={toggle} />
			</aside>
		{/if}
	</div>
</div>

<style>
	.search-page {
		max-width: 1120px;
		margin: 0 auto;
		padding: var(--space-10) var(--space-6);
	}

	.search-header {
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

	.summary code {
		font: var(--type-mono-sm);
		color: var(--text-primary);
	}

	.result-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		flex-wrap: wrap;
		margin-top: var(--space-4);
	}

	.result-count {
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.result-count .mono {
		font: var(--type-mono-md);
		color: var(--text-primary);
	}

	.result-actions {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.refine-toggle {
		display: none;
	}

	.search-body.with-rail {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 260px;
		gap: var(--space-8);
		align-items: start;
	}

	.refine-rail {
		position: sticky;
		top: var(--space-6);
	}

	.results {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		list-style: none;
	}

	.result {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		background: var(--bg-surface);
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint);
	}

	.result:hover,
	.result:focus-within {
		background: var(--bg-raised);
		border-color: var(--border-default);
	}

	.result-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
		padding-right: 136px;
		font: var(--type-label-sm);
		color: var(--text-tertiary);
	}

	.author {
		color: var(--text-primary);
		font: var(--type-label-md);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.channel {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		color: var(--text-secondary);
		white-space: nowrap;
	}

	a.author:hover,
	.channel:hover {
		color: var(--accent);
	}

	time {
		margin-left: auto;
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	.snippet {
		font: var(--type-body-md);
		color: var(--text-secondary);
		overflow-wrap: anywhere;
	}

	.snippet mark {
		background: var(--accent-muted);
		color: var(--accent);
		border-radius: 2px;
		padding: 0 1px;
	}

	.attachments {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-label-sm);
		color: var(--text-tertiary);
	}

	/* "Open in context" rises in on hover or keyboard focus within the row. */
	.open-context {
		position: absolute;
		top: var(--space-2);
		right: var(--space-2);
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		height: 28px;
		padding: 0 var(--space-2);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		background: var(--bg-overlay);
		color: var(--text-primary);
		font: var(--type-label-sm);
		white-space: nowrap;
		opacity: 0;
		transform: translateY(4px);
		transition:
			opacity var(--duration-micro) var(--ease-out-quint),
			transform var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint);
	}

	.result:hover .open-context,
	.result:focus-within .open-context {
		opacity: 1;
		transform: none;
	}

	.open-context:hover {
		border-color: var(--accent-glow);
		color: var(--accent);
	}

	/* Without hover, the action is always there. */
	@media (hover: none) {
		.open-context {
			position: static;
			align-self: flex-start;
			opacity: 1;
			transform: none;
		}

		.result-meta {
			padding-right: 0;
		}
	}

	@media (max-width: 1023px) {
		.search-body.with-rail {
			display: flex;
			flex-direction: column-reverse;
			gap: var(--space-4);
		}

		.refine-toggle {
			display: inline-flex;
		}

		.refine-rail {
			position: static;
			display: none;
			width: 100%;
			padding: var(--space-4);
			border: 1px solid var(--border-subtle);
			border-radius: var(--radius-md);
			background: var(--bg-surface);
		}

		.refine-rail.expanded {
			display: block;
		}
	}

	@media (max-width: 600px) {
		.search-page {
			padding: var(--space-6) var(--space-4);
		}

		.result {
			padding: var(--space-3);
		}

		.result-meta {
			flex-wrap: wrap;
			padding-right: 0;
		}

		time {
			margin-left: 0;
			width: 100%;
		}

		.open-context {
			position: static;
			align-self: flex-start;
			opacity: 1;
			transform: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.open-context {
			transform: none;
		}
	}
</style>
