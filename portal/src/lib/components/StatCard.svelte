<script lang="ts">
	import CountUp from './ui/CountUp.svelte';
	import Icon from './ui/Icon.svelte';
	import type { IconName } from './ui/icons.ts';

	let {
		label,
		value,
		icon,
		sub = '',
		index = 0,
		countUp = false,
		change = null,
		changeLabel = '',
		changeTitle
	}: {
		label: string;
		value: string | number;
		icon?: IconName;
		sub?: string;
		/** The tile's place in its row, for the staggered first paint. */
		index?: number;
		/** Count a numeric value up from zero when the tile first paints. */
		countUp?: boolean;
		/** A signed change to show under the value, or null for none (not zero). */
		change?: number | null;
		/** What the change is measured from, e.g. "since last scrape". */
		changeLabel?: string;
		/** A longer description of the change, as its tooltip. */
		changeTitle?: string;
	} = $props();

	const direction = $derived(change === null ? '' : change > 0 ? 'up' : change < 0 ? 'down' : 'flat');
	const changeText = $derived.by(() => {
		if (change === null) return '';
		if (change === 0) return `No change ${changeLabel}`.trim();
		const sign = change > 0 ? '+' : '−';
		return `${sign}${Math.abs(change).toLocaleString()} ${changeLabel}`.trim();
	});
</script>

<div class="stat-card enter" style:--i={index}>
	<div class="stat-head">
		<span class="stat-label">{label}</span>
		{#if icon}<Icon name={icon} />{/if}
	</div>
	<div class="stat-value mono">
		{#if countUp && typeof value === 'number'}<CountUp {value} />{:else}{typeof value === 'number'
				? value.toLocaleString()
				: value}{/if}
	</div>
	{#if change !== null}
		<div class="stat-change {direction}" title={changeTitle}>
			{#if direction === 'up'}<Icon name="arrow-up-right" size={14} />{/if}
			<span class="mono">{changeText}</span>
		</div>
	{/if}
	{#if sub}
		<div class="stat-sub mono">{sub}</div>
	{/if}
</div>

<style>
	.stat-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		padding: var(--space-4) var(--space-5);
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.stat-card:hover {
		border-color: var(--border-default);
	}

	.stat-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
		color: var(--text-secondary);
	}

	.stat-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-secondary);
	}

	.stat-value {
		font: var(--type-mono-num-lg);
		color: var(--text-primary);
	}

	.stat-change {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		font: var(--type-mono-sm);
		color: var(--text-secondary);
	}

	/* The arrow carries the direction; the text stays in text ink. */
	.stat-change.up :global(.icon) {
		color: var(--success);
	}

	.stat-change.flat {
		color: var(--text-tertiary);
	}

	.stat-sub {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}
</style>
