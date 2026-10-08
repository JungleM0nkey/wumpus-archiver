<script lang="ts">
	import Icon from './ui/Icon.svelte';
	import IconButton from './ui/IconButton.svelte';
	import Kbd from './ui/Kbd.svelte';

	let {
		value = $bindable(''),
		placeholder = 'Search the archive...',
		label = 'Search',
		onsubmit,
	}: {
		value?: string;
		placeholder?: string;
		/** The field's accessible name. */
		label?: string;
		onsubmit?: (query: string) => void;
	} = $props();

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && value.trim()) {
			onsubmit?.(value.trim());
		}
	}
</script>

<div class="search-bar">
	<Icon name="search" size={18} />
	<input
		type="search"
		bind:value
		{placeholder}
		aria-label={label}
		onkeydown={handleKeydown}
		class="search-input"
	/>
	{#if value}
		<IconButton icon="x" label="Clear search" size="sm" onclick={() => (value = '')} />
	{/if}
	<div class="search-hint">
		<Kbd>Enter</Kbd> to search
	</div>
</div>

<style>
	.search-bar {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		height: 44px;
		padding: 0 var(--space-2) 0 var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		color: var(--text-tertiary);
		transition:
			border-color var(--duration-micro) var(--ease-out-quint),
			box-shadow var(--duration-micro) var(--ease-out-quint);
	}

	.search-bar:hover {
		border-color: var(--border-strong);
	}

	/* The field's focus ring sits on the whole bar. */
	.search-bar:focus-within {
		border-color: var(--accent-glow);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}

	.search-input {
		flex: 1;
		min-width: 0;
		height: 100%;
		font: var(--type-body-md);
		color: var(--text-primary);
	}

	.search-input:focus-visible {
		outline: none;
	}

	.search-input::-webkit-search-cancel-button {
		display: none;
	}

	.search-input::placeholder {
		color: var(--text-tertiary);
	}

	.search-hint {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		padding-right: var(--space-2);
		font: var(--type-label-xs);
		color: var(--text-tertiary);
		white-space: nowrap;
	}
</style>
