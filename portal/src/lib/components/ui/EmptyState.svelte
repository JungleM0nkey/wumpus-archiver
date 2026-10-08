<!--
	What a view shows when it has nothing to show: an icon, a title, an optional line of
	explanation and optional actions.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.ts';

	let {
		icon = 'inbox',
		title,
		description,
		compact = false,
		children
	}: {
		icon?: IconName;
		title: string;
		description?: string;
		/** Less padding, for an empty state inside a card. */
		compact?: boolean;
		children?: Snippet;
	} = $props();
</script>

<div class="empty-state" class:compact>
	<span class="glyph"><Icon name={icon} size={20} /></span>
	<p class="title">{title}</p>
	{#if description}
		<p class="description">{description}</p>
	{/if}
	{#if children}
		<div class="actions">{@render children()}</div>
	{/if}
</div>

<style>
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-16) var(--space-4);
		text-align: center;
	}

	.compact {
		padding: var(--space-8) var(--space-4);
	}

	.glyph {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		margin-bottom: var(--space-1);
		border-radius: var(--radius-full);
		background: var(--bg-raised);
		border: 1px solid var(--border-subtle);
		color: var(--text-tertiary);
	}

	.title {
		font: var(--type-heading-sm);
		color: var(--text-primary);
	}

	.description {
		max-width: 360px;
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.actions {
		display: flex;
		gap: var(--space-2);
		margin-top: var(--space-2);
	}
</style>
