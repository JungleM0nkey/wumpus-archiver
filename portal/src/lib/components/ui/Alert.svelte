<!--
	A notice in the flow of a page: Warning, Danger or Info. A Danger alert is announced
	as it appears.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.ts';

	let {
		tone = 'info',
		title,
		children
	}: {
		tone?: 'warning' | 'danger' | 'info';
		title?: string;
		children?: Snippet;
	} = $props();

	const icons: Record<typeof tone, IconName> = {
		warning: 'triangle-alert',
		danger: 'octagon-alert',
		info: 'info'
	};
</script>

<div class="alert {tone}" role={tone === 'danger' ? 'alert' : undefined}>
	<span class="glyph"><Icon name={icons[tone]} size={18} /></span>
	<div class="body">
		{#if title}<p class="title">{title}</p>{/if}
		{#if children}<div class="text">{@render children()}</div>{/if}
	</div>
</div>

<style>
	.alert {
		--tone: var(--info);
		display: flex;
		align-items: flex-start;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		border: 1px solid color-mix(in srgb, var(--tone) 24%, transparent);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--tone) 8%, transparent);
	}

	.warning {
		--tone: var(--warning);
	}
	.danger {
		--tone: var(--danger);
	}

	.glyph {
		display: inline-flex;
		color: var(--tone);
		padding-top: 1px;
	}

	.body {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		min-width: 0;
	}

	.title {
		font: var(--type-label-md);
		line-height: 20px;
		color: var(--tone);
	}

	.text {
		font: var(--type-body-sm);
		color: var(--text-secondary);
		overflow-wrap: anywhere;
	}

	.text :global(code) {
		font-family: var(--font-mono);
		font-size: 12px;
		padding: 1px 5px;
		border-radius: var(--radius-xs);
		background: var(--bg-overlay);
		color: var(--text-primary);
	}
</style>
