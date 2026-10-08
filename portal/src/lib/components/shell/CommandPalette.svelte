<!--
	The command palette (Command- or Control-K): one field that jumps to a destination, a
	channel of the selected guild or a person (an author), or hands its text to Search. It
	opens from every screen (keyboard.svelte.ts) and reads what it lists only once it opens.

	Results re-rank as the query changes without moving anything: the dialog's top edge
	is fixed, the result list has a fixed height and every row the same height, and the
	highlighted result stays highlighted while it is still listed.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { getGuild, getGuildUsers } from '#lib/api.ts';
	import { overlays } from '#lib/keyboard.svelte.ts';
	import { ARCHIVE_HREF, channelHref, personHref } from '#lib/routes.ts';
	import { DESTINATIONS, shell } from '#lib/shell.svelte.ts';
	import { ChannelType, type Channel, type UserListItem } from '#lib/types.ts';
	import Dialog from '../ui/Dialog.svelte';
	import Icon from '../ui/Icon.svelte';
	import type { IconName } from '../ui/icons.ts';
	import Shortcut from '../ui/Shortcut.svelte';

	interface Result {
		key: string;
		label: string;
		detail?: string;
		icon: IconName;
		avatar?: string | null;
		href: string;
		/** How well the label matches the query: lower is better. */
		score: number;
	}

	interface Group {
		label: string;
		results: Result[];
	}

	/** How many channels and people the palette lists at most. */
	const LIMIT = 6;
	/** How long typing pauses before people are looked up. */
	const PEOPLE_DEBOUNCE_MS = 150;

	let query = $state('');
	let activeKey = $state('');
	let channels = $state<Channel[]>([]);
	let topPeople = $state<UserListItem[]>([]);
	let foundPeople = $state<{ q: string; people: UserListItem[] } | null>(null);
	let loadedFor = '';
	/** The read of the channels, while it is under way. */
	let channelsLoading: Promise<void> | null = null;

	/** The channels a reader opens: text, announcement and forum channels and threads. */
	const READABLE = new Set<number>([
		ChannelType.GUILD_TEXT,
		ChannelType.GUILD_ANNOUNCEMENT,
		ChannelType.GUILD_FORUM,
		ChannelType.PUBLIC_THREAD,
		ChannelType.PRIVATE_THREAD
	]);

	// What the palette lists is read when it opens, once per guild.
	$effect(() => {
		if (!overlays.palette) return;
		query = '';
		picked = false;
		const guild = shell.guild;
		if (!guild || loadedFor === guild.id) return;
		loadedFor = guild.id;
		channels = [];
		topPeople = [];
		foundPeople = null;
		channelsLoading = getGuild(guild.id)
			.then((detail) => {
				channels = detail.channels.filter((c) => READABLE.has(c.type));
			})
			.catch(() => {
				loadedFor = '';
			})
			.finally(() => (channelsLoading = null));
		getGuildUsers(guild.id, { limit: LIMIT })
			.then((res) => (topPeople = res.users))
			.catch(() => {});
	});

	// People who match the query, looked up once typing pauses.
	$effect(() => {
		const q = query.trim();
		const guild = shell.guild;
		if (!overlays.palette || !q || !guild) return;
		const timer = setTimeout(() => {
			getGuildUsers(guild.id, { q, limit: LIMIT })
				.then((res) => {
					if (query.trim() === q) foundPeople = { q, people: res.users };
				})
				.catch(() => {});
		}, PEOPLE_DEBOUNCE_MS);
		return () => clearTimeout(timer);
	});

	/**
	 * How well `text` matches `q`: 0 exactly, 1 as a prefix, 2 at a word's start, 3
	 * anywhere, 4 as letters in order; null when it does not.
	 */
	function score(text: string, q: string): number | null {
		if (!q) return 0;
		const t = text.toLowerCase();
		if (t === q) return 0;
		if (t.startsWith(q)) return 1;
		const at = t.indexOf(q);
		if (at > 0 && /[\s\-_./]/.test(t[at - 1])) return 2;
		if (at > 0) return 3;
		let i = 0;
		for (const ch of t) if (ch === q[i]) i++;
		return i === q.length ? 4 : null;
	}

	function ranked(results: Result[]): Result[] {
		return results
			.filter((r) => Number.isFinite(r.score))
			.sort((a, b) => a.score - b.score);
	}

	function personName(person: UserListItem): string {
		return person.display_name || person.global_name || person.username;
	}

	const groups = $derived.by((): Group[] => {
		const q = query.trim().toLowerCase();
		const destinations: Result[] = [
			...DESTINATIONS.map((d) => ({ key: `d:${d.href}`, label: d.label, icon: d.icon, href: d.href })),
			{ key: 'd:archive', label: 'Archive', detail: 'Scrape jobs and downloads', icon: 'archive' as const, href: ARCHIVE_HREF }
		].map((r) => ({ ...r, score: score(r.label, q) ?? Infinity }));

		const channelResults: Result[] = channels
			.map((c) => ({
				key: `c:${c.id}`,
				label: c.name,
				detail: `${c.message_count.toLocaleString()} messages`,
				icon: 'hash' as const,
				href: channelHref(c.id),
				score: (score(c.name, q) ?? Infinity) + (q ? 0 : -c.message_count / 1e9)
			}))
			.sort((a, b) => a.score - b.score);

		const people = q ? (foundPeople?.q.toLowerCase() === q ? foundPeople.people : []) : topPeople;
		const peopleResults: Result[] = people.map((p) => ({
			key: `p:${p.id}`,
			label: personName(p),
			detail: p.username !== personName(p) ? `@${p.username}` : undefined,
			icon: 'user' as const,
			avatar: p.avatar_url,
			href: personHref(p.id),
			// The API matched them; rank by the name it shows.
			score: Math.min(score(personName(p), q) ?? 4, score(p.username, q) ?? 4)
		}));

		const listed: Group[] = [
			{ label: 'Destinations', results: ranked(destinations) },
			{ label: 'Channels', results: ranked(channelResults).slice(0, LIMIT) },
			{ label: 'People', results: ranked(peopleResults).slice(0, LIMIT) }
		].filter((g) => g.results.length > 0);
		// A query ranks the groups by their best match; the default order breaks ties.
		if (q) listed.sort((a, b) => a.results[0].score - b.results[0].score);

		if (query.trim()) {
			listed.push({
				label: 'Search',
				results: [
					{
						key: 'search',
						label: `Search messages for “${query.trim()}”`,
						icon: 'search',
						href: `/search?q=${encodeURIComponent(query.trim())}`,
						score: 0
					}
				]
			});
		}
		return listed;
	});

	const flat = $derived(groups.flatMap((g) => g.results));

	/** Whether the reader picked the highlighted result (arrows, pointer) since the query changed. */
	let picked = false;

	// The best result is highlighted, unless the reader picked one that is still listed.
	$effect(() => {
		const results = flat;
		if (picked && results.some((r) => r.key === activeKey)) return;
		activeKey = results[0]?.key ?? '';
	});

	function pick(key: string) {
		picked = true;
		activeKey = key;
	}

	function optionId(key: string): string {
		return `palette-option-${key.replace(/[^\w-]/g, '_')}`;
	}

	function move(by: number) {
		if (flat.length === 0) return;
		const at = flat.findIndex((r) => r.key === activeKey);
		const next = (at + by + flat.length) % flat.length;
		pick(flat[next].key);
		document.getElementById(optionId(activeKey))?.scrollIntoView({ block: 'nearest' });
	}

	function choose(result: Result | undefined) {
		if (!result) return;
		overlays.palette = false;
		void goto(result.href);
	}

	/** Enter: open the highlighted result, once the channels are read if they are still loading. */
	async function enter() {
		if (channelsLoading) {
			await channelsLoading;
			await tick();
		}
		if (overlays.palette) choose(flat.find((r) => r.key === activeKey));
	}

	function onkeydown(event: KeyboardEvent) {
		switch (event.key) {
			case 'ArrowDown':
				move(1);
				break;
			case 'ArrowUp':
				move(-1);
				break;
			case 'Enter':
				void enter();
				break;
			default:
				return;
		}
		event.preventDefault();
	}
</script>

<Dialog bind:open={overlays.palette} label="Command palette" placement="top" initialFocus=".palette-input" id="command-palette">
	<div class="palette">
		<div class="field">
			<Icon name="search" size={18} />
			<input
				class="palette-input"
				type="text"
				role="combobox"
				aria-label="Jump to or search for"
				aria-expanded="true"
				aria-controls="palette-results"
				aria-autocomplete="list"
				aria-activedescendant={activeKey ? optionId(activeKey) : undefined}
				placeholder="Jump to a screen, channel or person, or search messages"
				autocomplete="off"
				spellcheck="false"
				bind:value={query}
				oninput={() => (picked = false)}
				{onkeydown}
			/>
			<button type="button" class="close" aria-label="Close" onclick={() => (overlays.palette = false)}>
				<Shortcut keys={['Esc']} />
			</button>
		</div>

		<div class="results" id="palette-results" role="listbox" aria-label="Results">
			{#each groups as group (group.label)}
				{@const groupId = `palette-group-${group.label.toLowerCase()}`}
				<div class="group" role="group" aria-labelledby={groupId}>
					<div class="group-label" id={groupId}>{group.label}</div>
					{#each group.results as result (result.key)}
						<!-- svelte-ignore a11y_click_events_have_key_events (the field handles keys) -->
						<div
							id={optionId(result.key)}
							class="option"
							class:active={result.key === activeKey}
							role="option"
							tabindex="-1"
							aria-selected={result.key === activeKey}
							onclick={() => choose(result)}
							onpointermove={() => result.key !== activeKey && pick(result.key)}
						>
							{#if result.avatar}
								<img class="avatar" src={result.avatar} alt="" />
							{:else}
								<span class="glyph"><Icon name={result.icon} /></span>
							{/if}
							<span class="label truncate">{result.label}</span>
							{#if result.detail}<span class="detail truncate">{result.detail}</span>{/if}
							<span class="enter" aria-hidden="true"><Icon name="corner-down-left" size={14} /></span>
						</div>
					{/each}
				</div>
			{:else}
				<p class="empty">Nothing to jump to yet.</p>
			{/each}
		</div>

		<div class="hints" aria-hidden="true">
			<span><Shortcut keys={['Up', 'Down']} /> to move</span>
			<span><Shortcut keys={['Enter']} /> to open</span>
			<span class="push"><Shortcut keys={['?']} /> for shortcuts</span>
		</div>
	</div>
</Dialog>

<style>
	.palette {
		display: flex;
		flex-direction: column;
	}

	.field {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		height: 52px;
		padding: 0 var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
		color: var(--text-tertiary);
	}

	.palette-input {
		flex: 1;
		min-width: 0;
		height: 100%;
		font: var(--type-body-md);
		color: var(--text-primary);
		outline: none;
	}

	.palette-input::placeholder {
		color: var(--text-tertiary);
	}

	.close {
		display: inline-flex;
		padding: var(--space-1);
		margin-right: calc(-1 * var(--space-1));
		border-radius: var(--radius-sm);
	}

	.close:hover :global(.kbd) {
		color: var(--text-primary);
		border-color: var(--border-strong);
	}

	/* A fixed height: results come and go and re-rank inside it, never resizing it. */
	.results {
		height: min(360px, calc(100dvh - 220px));
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: var(--space-2);
	}

	.group + .group {
		margin-top: var(--space-2);
	}

	.group-label {
		height: 28px;
		display: flex;
		align-items: center;
		padding: 0 var(--space-2);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.option {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		height: 40px;
		padding: 0 var(--space-2);
		border-radius: var(--radius-sm);
		color: var(--text-secondary);
		cursor: pointer;
	}

	.option.active {
		background: var(--bg-active);
		color: var(--text-primary);
	}

	.glyph {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		flex-shrink: 0;
		border-radius: var(--radius-xs);
		background: var(--bg-inset);
	}

	.option.active .glyph {
		color: var(--accent);
	}

	.avatar {
		width: 24px;
		height: 24px;
		flex-shrink: 0;
		border-radius: var(--radius-full);
		object-fit: cover;
	}

	.label {
		font: var(--type-label-md);
		color: var(--text-primary);
		min-width: 0;
	}

	.detail {
		flex: 1;
		min-width: 0;
		font: var(--type-body-sm);
		color: var(--text-tertiary);
	}

	.enter {
		display: inline-flex;
		margin-left: auto;
		color: var(--text-tertiary);
		visibility: hidden;
	}

	.option.active .enter {
		visibility: visible;
	}

	.empty {
		padding: var(--space-4) var(--space-2);
		font: var(--type-body-sm);
		color: var(--text-tertiary);
	}

	.hints {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		height: 40px;
		padding: 0 var(--space-4);
		border-top: 1px solid var(--border-subtle);
		font: var(--type-label-sm);
		color: var(--text-tertiary);
	}

	.hints span {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
	}

	.hints .push {
		margin-left: auto;
	}

	@media (max-width: 767px) {
		.hints {
			display: none;
		}
	}
</style>
