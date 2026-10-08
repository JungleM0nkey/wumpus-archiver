<script lang="ts">
	import Icon from './ui/Icon.svelte';
	import type { IconName } from './ui/icons.ts';

	let {
		label,
		value,
		icon,
		sub = '',
		index = 0
	}: {
		label: string;
		value: string | number;
		icon?: IconName;
		sub?: string;
		/** The tile's place in its row, for the staggered first paint. */
		index?: number;
	} = $props();
</script>

<div class="stat-card enter" style:--i={index}>
	<div class="stat-head">
		<span class="stat-label">{label}</span>
		{#if icon}<Icon name={icon} />{/if}
	</div>
	<div class="stat-value mono">{typeof value === 'number' ? value.toLocaleString() : value}</div>
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

	.stat-sub {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}
</style>
