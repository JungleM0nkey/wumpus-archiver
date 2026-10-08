<!--
	One icon from the portal's set (icons.ts): a 1.75px-stroke Lucide icon drawn in the
	current text colour at 16, 18 or 20px. It is decorative unless given a `label`.
-->
<script lang="ts">
	import { icons, type IconName } from './icons.ts';

	let {
		name,
		size = 16,
		label
	}: {
		name: IconName;
		size?: 14 | 16 | 18 | 20 | 24 | 32;
		/** What the icon means, for an icon that stands alone; omit when text says it. */
		label?: string;
	} = $props();

	const Glyph = $derived(icons[name]);
</script>

{#if label}
	<Glyph {size} strokeWidth={1.75} class="icon" role="img" aria-label={label} />
{:else}
	<Glyph {size} strokeWidth={1.75} class="icon" aria-hidden="true" />
{/if}
