<!--
	A small label in one of six tones. `mono` sets it in the mono face, for counts and ids.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.ts';

	let {
		tone = 'neutral',
		icon,
		mono = false,
		title,
		children
	}: {
		tone?: 'neutral' | 'accent' | 'success' | 'danger' | 'warning' | 'info';
		icon?: IconName;
		mono?: boolean;
		title?: string;
		children: Snippet;
	} = $props();
</script>

<span class="badge {tone}" class:mono {title}>
	{#if icon}<Icon name={icon} size={14} />{/if}
	<span class="text">{@render children()}</span>
</span>

<style>
	.badge {
		--tone: var(--text-secondary);
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		min-width: 0;
		max-width: 100%;
		height: 20px;
		padding: 0 6px;
		border: 1px solid color-mix(in srgb, var(--tone) 24%, transparent);
		border-radius: var(--radius-xs);
		background: color-mix(in srgb, var(--tone) 12%, transparent);
		color: var(--tone);
		font: var(--type-label-xs);
		white-space: nowrap;
	}

	.text {
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.mono {
		font-family: var(--font-mono);
		font-variant-numeric: tabular-nums;
	}

	.neutral {
		background: var(--bg-overlay);
		border-color: var(--border-subtle);
	}
	.accent {
		--tone: var(--accent);
	}
	.success {
		--tone: var(--success);
	}
	.danger {
		--tone: var(--danger);
	}
	.warning {
		--tone: var(--warning);
	}
	.info {
		--tone: var(--info);
	}
</style>
