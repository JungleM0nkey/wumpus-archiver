<script lang="ts">
	let {
		value = $bindable(''),
		placeholder = 'Search the archive...',
		onsubmit,
	}: {
		value?: string;
		placeholder?: string;
		onsubmit?: (query: string) => void;
	} = $props();

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && value.trim()) {
			onsubmit?.(value.trim());
		}
	}
</script>

<div class="search-bar">
	<span class="search-icon">⌕</span>
	<input
		type="text"
		bind:value
		{placeholder}
		onkeydown={handleKeydown}
		class="search-input"
	/>
	{#if value}
		<button class="clear-btn" onclick={() => (value = '')}>✕</button>
	{/if}
	<div class="search-hint mono">
		<kbd>↵</kbd> search
	</div>
</div>

<style>
	.search-bar {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-3) var(--sp-4);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		transition: border-color 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
	}

	.search-bar:focus-within {
		border-color: var(--border-accent);
		box-shadow: 0 0 0 3px var(--accent-glow);
	}

	.search-icon {
		font-size: 18px;
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.search-input {
		flex: 1;
		font-size: 15px;
		color: var(--text-primary);
		min-width: 0;
	}

	.search-input::placeholder {
		color: var(--text-muted);
	}

	.clear-btn {
		padding: var(--sp-1) var(--sp-2);
		color: var(--text-muted);
		font-size: 13px;
		border-radius: var(--radius-sm);
		transition: all 0.15s var(--ease-out);
	}

	.clear-btn:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.search-hint {
		display: flex;
		align-items: center;
		gap: var(--sp-1);
		font-size: 11px;
		color: var(--text-faint);
		white-space: nowrap;
	}

	.search-hint kbd {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 20px;
		padding: 1px 5px;
		background: var(--bg-raised);
		border: 1px solid var(--border);
		border-radius: 3px;
		font-family: var(--font-mono);
		font-size: 10px;
	}
</style>
