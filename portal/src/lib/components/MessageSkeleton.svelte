<!-- Message cards loading: skeletons in the shape of MessageCard. -->
<script lang="ts">
	import Skeleton from './ui/Skeleton.svelte';

	let { count = 4, label = 'Loading messages…' }: { count?: number; label?: string } = $props();

	// Varied line lengths, so the placeholders read as messages rather than a grid.
	const lines = ['92%', '64%', '78%', '48%', '86%', '58%'];
</script>

<div class="message-skeletons" aria-busy="true">
	<span class="sr-only" role="status">{label}</span>
	{#each Array.from({ length: count }, (_, i) => i) as i (i)}
		<div class="card">
			<div class="head">
				<Skeleton width="32px" height="32px" radius="full" />
				<Skeleton width="120px" height="12px" />
				<span class="spacer"></span>
				<Skeleton width="132px" height="10px" />
			</div>
			<Skeleton width={lines[i % lines.length]} height="12px" />
			{#if i % 2 === 0}
				<Skeleton width={lines[(i + 3) % lines.length]} height="12px" />
			{/if}
		</div>
	{/each}
</div>

<style>
	.message-skeletons {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.card {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4) var(--space-5);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		background: var(--bg-surface);
	}

	.head {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.spacer {
		flex: 1;
	}
</style>
