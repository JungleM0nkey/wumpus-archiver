<!-- The button that loads the next page of a list, centred beneath (or above) it. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Button from './ui/Button.svelte';

	let {
		loading = false,
		onclick,
		children
	}: {
		loading?: boolean;
		onclick: () => void;
		children: Snippet;
	} = $props();
</script>

<div class="load-more">
	<Button variant="secondary" {loading} {onclick}>{@render children()}</Button>
</div>

<style>
	.load-more {
		display: flex;
		justify-content: center;
		padding: var(--space-6) 0;
	}
</style>
