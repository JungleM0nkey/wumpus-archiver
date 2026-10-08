<!--
	A button that is only an icon. Its `label` names it for assistive technology and
	shows as its tooltip.
-->
<script lang="ts">
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.ts';

	let {
		icon,
		label,
		variant = 'ghost',
		size = 'md',
		type = 'button',
		...rest
	}: Omit<HTMLButtonAttributes, 'class' | 'children'> & {
		icon: IconName;
		label: string;
		variant?: 'ghost' | 'secondary' | 'overlay';
		size?: 'sm' | 'md' | 'lg';
	} = $props();

	const iconSize = $derived(size === 'sm' ? 14 : size === 'lg' ? 24 : 16);
</script>

<button {...rest} {type} class="icon-button {variant} {size}" aria-label={label} title={label}>
	<Icon name={icon} size={iconSize} />
</button>

<style>
	.icon-button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		border: 1px solid transparent;
		border-radius: var(--radius-sm);
		color: var(--text-secondary);
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint),
			transform var(--duration-micro) var(--ease-out-quint);
	}

	.icon-button:hover:not(:disabled) {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.icon-button:active:not(:disabled) {
		transform: scale(0.98);
	}

	.icon-button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.sm {
		width: 28px;
		height: 28px;
	}

	.md {
		width: 32px;
		height: 32px;
	}

	.lg {
		width: 44px;
		height: 44px;
		border-radius: var(--radius-full);
	}

	.secondary {
		background: var(--bg-raised);
		border-color: var(--border-default);
	}

	/* On a scrim: the lightbox's close and arrows. */
	.overlay {
		background: rgba(0, 0, 0, 0.45);
		color: var(--text-primary);
	}
	.overlay:hover:not(:disabled) {
		background: rgba(0, 0, 0, 0.7);
	}
</style>
