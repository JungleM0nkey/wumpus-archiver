<!-- The narrow layout's bottom tab bar: the five destinations (shell.svelte.ts). -->
<script lang="ts">
	import { page } from '$app/state';
	import { DESTINATIONS, withGuild } from '#lib/shell.svelte.ts';
	import Icon from '../ui/Icon.svelte';
</script>

<nav class="tab-bar" aria-label="Tab bar">
	{#each DESTINATIONS as destination (destination.href)}
		{@const active = destination.owns(page.url.pathname)}
		<a
			href={withGuild(destination.href)}
			class="tab"
			class:active
			aria-current={active ? 'page' : undefined}
		>
			<Icon name={destination.icon} size={20} />
			<span class="tab-label">{destination.label}</span>
		</a>
	{/each}
</nav>

<style>
	.tab-bar {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		height: calc(var(--size-tabbar) + env(safe-area-inset-bottom, 0px));
		padding-bottom: env(safe-area-inset-bottom, 0px);
		background: var(--bg-surface);
		border-top: 1px solid var(--border-subtle);
	}

	.tab {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 3px;
		min-width: 0;
		color: var(--text-tertiary);
		transition: color var(--duration-micro) var(--ease-out-quint);
	}

	.tab:hover {
		color: var(--text-primary);
	}

	.tab.active {
		color: var(--text-primary);
	}

	.tab.active :global(.icon) {
		color: var(--accent);
	}

	.tab-label {
		font: var(--type-label-xs);
	}
</style>
