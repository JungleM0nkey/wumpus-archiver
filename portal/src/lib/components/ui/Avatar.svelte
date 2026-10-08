<!--
	A person's avatar, or their initial on a plain disc when the archive has no image.
	It is decorative (the name is always shown beside it), so it carries no alt text.
-->
<script lang="ts">
	let {
		src,
		name,
		size = 32
	}: {
		src: string | null | undefined;
		/** The name shown beside it; its first letter stands in for a missing image. */
		name: string;
		/** Diameter in px. */
		size?: number;
	} = $props();

	let failed = $state(false);
	const initial = $derived((name.trim()[0] ?? '?').toUpperCase());
</script>

{#if src && !failed}
	<img
		class="avatar"
		{src}
		alt=""
		loading="lazy"
		style:width="{size}px"
		style:height="{size}px"
		onerror={() => (failed = true)}
	/>
{:else}
	<span
		class="avatar fallback"
		aria-hidden="true"
		style:width="{size}px"
		style:height="{size}px"
		style:font-size="{Math.round(size * 0.42)}px">{initial}</span
	>
{/if}

<style>
	.avatar {
		display: inline-flex;
		flex-shrink: 0;
		border-radius: var(--radius-full);
		object-fit: cover;
		background: var(--bg-overlay);
	}

	.fallback {
		align-items: center;
		justify-content: center;
		color: var(--text-secondary);
		font-family: var(--font-sans);
		font-weight: 600;
		line-height: 1;
	}
</style>
