<!--
	The Search screen's refine rail: how the results divide by channel, by person and by
	month. Each entry is a toggle for its chips: picking one adds them to the query, and
	picking one in force takes them off again.
-->
<script lang="ts">
	import Avatar from '../ui/Avatar.svelte';
	import Icon from '../ui/Icon.svelte';
	import { chipValue, monthChips, type Chip, type SearchQuery } from '#lib/search.ts';
	import type { SearchFacets } from '#lib/types.ts';

	let {
		facets,
		query,
		ontoggle
	}: {
		facets: SearchFacets;
		query: SearchQuery;
		/** Add `chips`, or take them off when they are all in force. */
		ontoggle: (chips: Chip[]) => void;
	} = $props();

	/** Whether every chip of `chips` is in force, matched without regard to case. */
	function applied(chips: Chip[]): boolean {
		return chips.every((chip) => chipValue(query, chip.kind)?.toLowerCase() === chip.value.toLowerCase());
	}

	const MONTH = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });

	function monthLabel(start: string): string {
		return MONTH.format(new Date(`${start}T00:00:00Z`));
	}

	/** Every month from the first match's to the last's, empty ones included, up to ten years. */
	const months = $derived.by(() => {
		const found = facets.months;
		if (!found.length) return [];
		const counts = new Map(found.map((m) => [m.start, m.count]));
		const [y0, m0] = found[0].start.split('-').map(Number);
		const [y1, m1] = found[found.length - 1].start.split('-').map(Number);
		const span = (y1 - y0) * 12 + (m1 - m0) + 1;
		if (span > 120) return found;
		return Array.from({ length: span }, (_, i) => {
			const start = new Date(Date.UTC(y0, m0 - 1 + i, 1)).toISOString().slice(0, 10);
			return { start, count: counts.get(start) ?? 0 };
		});
	});
	const busiest = $derived(Math.max(1, ...months.map((m) => m.count)));
	const channelMax = $derived(Math.max(1, ...facets.channels.map((c) => c.count)));
	const authorMax = $derived(Math.max(1, ...facets.authors.map((a) => a.count)));
</script>

<div class="refine">
	{#if facets.channels.length}
		<section class="facet" aria-labelledby="facet-channels">
			<h2 id="facet-channels" class="facet-title">Channels</h2>
			<ul class="facet-list">
				{#each facets.channels as channel (channel.id)}
					{@const chips = [{ kind: 'in' as const, value: channel.name }]}
					<li>
						<button
							type="button"
							class="facet-row"
							aria-pressed={applied(chips)}
							aria-label={`#${channel.name}: ${channel.count} ${channel.count === 1 ? 'result' : 'results'}`}
							onclick={() => ontoggle(chips)}
						>
							<span class="share" style:width="{(channel.count / channelMax) * 100}%"></span>
							<Icon name="hash" size={14} />
							<span class="facet-name">{channel.name}</span>
							<span class="facet-count mono">{channel.count.toLocaleString()}</span>
						</button>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if facets.authors.length}
		<section class="facet" aria-labelledby="facet-people">
			<h2 id="facet-people" class="facet-title">People</h2>
			<ul class="facet-list">
				{#each facets.authors as author (author.id)}
					{@const chips = [{ kind: 'from' as const, value: author.username }]}
					<li>
						<button
							type="button"
							class="facet-row"
							aria-pressed={applied(chips)}
							aria-label={`${author.display_name}: ${author.count} ${author.count === 1 ? 'result' : 'results'}`}
							onclick={() => ontoggle(chips)}
						>
							<span class="share" style:width="{(author.count / authorMax) * 100}%"></span>
							<Avatar src={author.avatar_url} name={author.display_name} size={18} />
							<span class="facet-name">{author.display_name}</span>
							<span class="facet-count mono">{author.count.toLocaleString()}</span>
						</button>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if months.length}
		<section class="facet" aria-labelledby="facet-months">
			<h2 id="facet-months" class="facet-title">When</h2>
			<div class="histogram" role="group" aria-labelledby="facet-months">
				{#each months as month (month.start)}
					{@const chips = monthChips(month.start)}
					<button
						type="button"
						class="bar"
						aria-pressed={applied(chips)}
						aria-label={`${monthLabel(month.start)}: ${month.count} ${month.count === 1 ? 'result' : 'results'}`}
						title={`${monthLabel(month.start)}: ${month.count.toLocaleString()}`}
						disabled={month.count === 0}
						onclick={() => ontoggle(chips)}
					>
						<span class="bar-fill" style:height="{Math.max(month.count ? 8 : 2, (month.count / busiest) * 100)}%"></span>
					</button>
				{/each}
			</div>
			<div class="histogram-axis mono">
				<span>{monthLabel(months[0].start)}</span>
				{#if months.length > 1}<span>{monthLabel(months[months.length - 1].start)}</span>{/if}
			</div>
		</section>
	{/if}
</div>

<style>
	.refine {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.facet-title {
		margin-bottom: var(--space-2);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.facet-list {
		display: flex;
		flex-direction: column;
		gap: 2px;
		list-style: none;
	}

	.facet-row {
		position: relative;
		display: flex;
		align-items: center;
		gap: var(--space-2);
		width: 100%;
		height: 30px;
		padding: 0 var(--space-2);
		border-radius: var(--radius-sm);
		color: var(--text-secondary);
		font: var(--type-label-md);
		text-align: left;
		isolation: isolate;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.facet-row:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.facet-row[aria-pressed='true'] {
		background: var(--accent-muted);
		color: var(--accent);
	}

	/* The entry's share of the busiest entry, drawn faintly behind it. */
	.share {
		position: absolute;
		inset: 3px auto 3px 0;
		z-index: -1;
		border-radius: var(--radius-xs);
		background: var(--bg-raised);
	}

	.facet-row[aria-pressed='true'] .share {
		background: transparent;
	}

	.facet-name {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.facet-count {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.histogram {
		display: flex;
		align-items: flex-end;
		gap: 2px;
		height: 64px;
	}

	.bar {
		flex: 1;
		display: flex;
		align-items: flex-end;
		height: 100%;
		min-width: 3px;
		border-radius: var(--radius-xs);
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.bar:not(:disabled):hover {
		background: var(--bg-hover);
	}

	.bar-fill {
		width: 100%;
		border-radius: var(--radius-xs) var(--radius-xs) 0 0;
		background: var(--border-strong);
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.bar:not(:disabled):hover .bar-fill {
		background: var(--text-secondary);
	}

	.bar[aria-pressed='true'] .bar-fill {
		background: var(--accent);
	}

	.histogram-axis {
		display: flex;
		justify-content: space-between;
		margin-top: var(--space-1);
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}
</style>
