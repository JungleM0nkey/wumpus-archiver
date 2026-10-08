<!--
	Weekly activity as a heatmap: one cell per week, oldest first, shaded on the
	--heat-0…4 ramp relative to the busiest week. It is a one-row ARIA grid whose cells
	are labelled with their week and count. The cells are one tab stop; the arrow keys,
	Home and End move between weeks. The line under the cells reads out the week in
	focus or under the pointer, otherwise a summary of the whole range.
-->
<script lang="ts">
	import type { UserWeeklyActivity } from '#lib/types.ts';

	let {
		weeks,
		label
	}: {
		weeks: UserWeeklyActivity[];
		/** The heatmap's accessible name, such as "Alice's weekly activity". */
		label: string;
	} = $props();

	const DAY_MS = 24 * 60 * 60 * 1000;

	// Week dates are calendar dates (UTC Mondays), so they are read and printed in UTC.
	function day(iso: string, offsetDays = 0): Date {
		return new Date(Date.parse(`${iso}T00:00:00Z`) + offsetDays * DAY_MS);
	}

	function formatDay(date: Date): string {
		return date.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	function messages(count: number): string {
		return `${count.toLocaleString()} ${count === 1 ? 'message' : 'messages'}`;
	}

	function weekLabel(week: UserWeeklyActivity): string {
		return `Week of ${formatDay(day(week.week))}: ${messages(week.count)}`;
	}

	const max = $derived(Math.max(1, ...weeks.map((w) => w.count)));
	const total = $derived(weeks.reduce((sum, w) => sum + w.count, 0));
	const busiest = $derived(
		weeks.reduce<UserWeeklyActivity | null>((best, w) => (w.count > (best?.count ?? 0) ? w : best), null)
	);
	const rangeEnd = $derived(weeks.length ? formatDay(day(weeks[weeks.length - 1].week, 6)) : '');

	function level(count: number): number {
		return count === 0 ? 0 : Math.min(4, Math.ceil((count / max) * 4));
	}

	// A month's name above the week its first Monday falls in, unless it would crowd the next.
	const months = $derived.by(() => {
		const marks: { column: number; name: string }[] = [];
		weeks.forEach((w, i) => {
			const month = day(w.week).getUTCMonth();
			if (i > 0 && month === day(weeks[i - 1].week).getUTCMonth()) return;
			marks.push({
				column: i + 1,
				name: day(w.week).toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' })
			});
		});
		return marks.filter((mark, i) => (marks[i + 1]?.column ?? Infinity) - mark.column >= 3);
	});

	let focused = $state<number | null>(null);
	let hovered = $state<number | null>(null);
	let current = $state<number | null>(null);
	const tabStop = $derived(current ?? weeks.length - 1);
	const shown = $derived(hovered ?? focused);
	let cells: HTMLElement[] = $state([]);

	function onkeydown(event: KeyboardEvent) {
		const keys: Record<string, number> = {
			ArrowLeft: tabStop - 1,
			ArrowRight: tabStop + 1,
			Home: 0,
			End: weeks.length - 1
		};
		if (!(event.key in keys)) return;
		event.preventDefault();
		const next = Math.max(0, Math.min(weeks.length - 1, keys[event.key]));
		current = next;
		cells[next]?.focus();
	}
</script>

<figure class="heatmap">
	<div class="months" aria-hidden="true">
		{#each months as mark (mark.column)}
			<span style:grid-column="{mark.column} / span 3">{mark.name}</span>
		{/each}
	</div>
	<!-- The grid itself is not a tab stop; its current cell is. -->
	<div class="cells" role="grid" aria-label={label} tabindex="-1" {onkeydown}>
		<div class="row" role="row">
			{#each weeks as week, i (week.week)}
				<span
					bind:this={cells[i]}
					class="cell"
					class:shown={shown === i}
					role="gridcell"
					aria-label={weekLabel(week)}
					data-level={level(week.count)}
					tabindex={i === tabStop ? 0 : -1}
					onfocus={() => {
						focused = i;
						current = i;
					}}
					onblur={() => (focused = null)}
					onpointerenter={() => (hovered = i)}
					onpointerleave={() => (hovered = null)}
				></span>
			{/each}
		</div>
	</div>
	<figcaption class="caption">
		<span class="detail mono">
			{#if shown !== null && weeks[shown]}
				{weekLabel(weeks[shown])}
			{:else}
				{messages(total)} in the {weeks.length} weeks to {rangeEnd}{#if busiest}; busiest
					the week of {formatDay(day(busiest.week))}, {busiest.count.toLocaleString()}{/if}
			{/if}
		</span>
		<span class="legend" aria-hidden="true">
			Less
			{#each [0, 1, 2, 3, 4] as l (l)}
				<span class="cell" data-level={l}></span>
			{/each}
			More
		</span>
	</figcaption>
</figure>

<style>
	.heatmap {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
	}

	.months,
	.row {
		display: grid;
		grid-template-columns: repeat(52, minmax(0, 1fr));
		gap: 3px;
	}

	.months {
		font: var(--type-label-xs);
		color: var(--text-tertiary);
		white-space: nowrap;
	}

	.cell {
		height: 28px;
		border-radius: 2px;
		background: var(--heat-0);
	}

	.cells .cell {
		outline-offset: 1px;
		transition: box-shadow var(--duration-micro) var(--ease-out-quint);
	}

	.cells .cell.shown {
		box-shadow: 0 0 0 1px var(--text-secondary);
	}

	.cell[data-level='1'] {
		background: var(--heat-1);
	}
	.cell[data-level='2'] {
		background: var(--heat-2);
	}
	.cell[data-level='3'] {
		background: var(--heat-3);
	}
	.cell[data-level='4'] {
		background: var(--heat-4);
	}

	.caption {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-4);
		flex-wrap: wrap;
		min-height: 18px;
	}

	.detail {
		font: var(--type-mono-sm);
		color: var(--text-secondary);
	}

	.legend {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		font: var(--type-label-xs);
		color: var(--text-tertiary);
	}

	.legend .cell {
		width: 10px;
		height: 10px;
	}

	/* Two rows of 26 weeks on a narrow screen; the month marks no longer line up. */
	@media (max-width: 600px) {
		.row {
			grid-template-columns: repeat(26, minmax(0, 1fr));
		}

		.row .cell {
			height: 18px;
		}

		.months {
			display: none;
		}
	}
</style>
