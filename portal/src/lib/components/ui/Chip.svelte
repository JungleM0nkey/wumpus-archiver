<!--
	A toggle chip for filters, sorts and view switches; `selected` marks the one in force
	and is exposed as aria-pressed.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.ts';

	let {
		selected = false,
		icon,
		type = 'button',
		children,
		...rest
	}: Omit<HTMLButtonAttributes, 'class'> & {
		selected?: boolean;
		icon?: IconName;
		children: Snippet;
	} = $props();
</script>

<button {...rest} {type} class="chip" class:selected aria-pressed={selected}>
	{#if icon}<Icon name={icon} size={14} />{/if}
	{@render children()}
</button>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		height: 28px;
		padding: 0 var(--space-3);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-full);
		background: transparent;
		color: var(--text-secondary);
		font: var(--type-label-sm);
		white-space: nowrap;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.chip:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.chip.selected {
		background: var(--accent-muted);
		border-color: var(--accent-glow);
		color: var(--accent);
	}
</style>
