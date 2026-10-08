<!--
	A button: Primary, Secondary, Ghost or Danger, in Md or Sm. While `loading` it is
	disabled, busy and says so.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.ts';

	let {
		variant = 'secondary',
		size = 'md',
		icon,
		loading = false,
		disabled = false,
		type = 'button',
		children,
		...rest
	}: Omit<HTMLButtonAttributes, 'class'> & {
		variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
		size?: 'md' | 'sm';
		icon?: IconName;
		loading?: boolean;
		children: Snippet;
	} = $props();
</script>

<button
	{...rest}
	{type}
	class="button {variant} {size}"
	disabled={disabled || loading}
	aria-busy={loading || undefined}
>
	{#if icon && !loading}
		<Icon name={icon} size={size === 'sm' ? 14 : 16} />
	{/if}
	{#if loading}Loading…{:else}{@render children()}{/if}
</button>

<style>
	.button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		border: 1px solid transparent;
		border-radius: var(--radius-sm);
		white-space: nowrap;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint),
			transform var(--duration-micro) var(--ease-out-quint);
	}

	.button:active:not(:disabled) {
		transform: scale(0.98);
	}

	.button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.md {
		height: 36px;
		padding: 0 var(--space-4);
		font: var(--type-label-md);
	}

	.sm {
		height: 28px;
		padding: 0 var(--space-3);
		font: var(--type-label-sm);
	}

	.primary {
		background: var(--accent);
		color: var(--on-accent);
	}
	.primary:hover:not(:disabled) {
		background: var(--accent-strong);
	}

	.secondary {
		background: var(--bg-raised);
		border-color: var(--border-default);
		color: var(--text-primary);
	}
	.secondary:hover:not(:disabled) {
		background: var(--bg-overlay);
		border-color: var(--border-strong);
	}

	.ghost {
		color: var(--text-secondary);
	}
	.ghost:hover:not(:disabled) {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.danger {
		background: color-mix(in srgb, var(--danger) 14%, transparent);
		border-color: color-mix(in srgb, var(--danger) 32%, transparent);
		color: var(--danger);
	}
	.danger:hover:not(:disabled) {
		background: color-mix(in srgb, var(--danger) 22%, transparent);
	}
</style>
