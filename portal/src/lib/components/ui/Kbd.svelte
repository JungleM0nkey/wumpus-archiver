<!-- A key on the keyboard, as in "Enter to search". -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<kbd class="kbd">{@render children()}</kbd>

<style>
	.kbd {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 20px;
		height: 20px;
		padding: 0 5px;
		border: 1px solid var(--border-default);
		border-bottom-width: 2px;
		border-radius: var(--radius-xs);
		background: var(--bg-raised);
		color: var(--text-secondary);
		font: var(--type-mono-sm);
	}
</style>
