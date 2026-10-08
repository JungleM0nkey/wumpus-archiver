<!--
	A placeholder block for content that is loading, shimmering until it arrives. Pages
	compose skeletons into the shape of what they will show; the skeletons themselves
	are hidden from assistive technology, so the page says "Loading…" once beside them.
-->
<script lang="ts">
	let {
		width = '100%',
		height = '14px',
		aspect,
		radius = 'xs'
	}: {
		width?: string;
		height?: string;
		/** An aspect ratio such as '1', for a placeholder sized by its width. */
		aspect?: string;
		radius?: 'xs' | 'sm' | 'md' | 'lg' | 'full';
	} = $props();
</script>

<span
	class="skeleton"
	style:width
	style:height={aspect ? undefined : height}
	style:aspect-ratio={aspect}
	style:border-radius="var(--radius-{radius})"
	aria-hidden="true"
></span>

<style>
	.skeleton {
		display: block;
		flex-shrink: 0;
		max-width: 100%;
		background: linear-gradient(
			90deg,
			var(--bg-raised) 25%,
			var(--bg-inset) 50%,
			var(--bg-raised) 75%
		);
		background-size: 200% 100%;
		animation: shimmer var(--duration-shimmer) linear infinite;
	}
</style>
