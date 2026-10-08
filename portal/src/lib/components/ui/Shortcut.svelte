<!--
	A keyboard shortcut as its keys, one Kbd each: `keys={['Mod', 'K']}`. `Mod` is the
	Command key on Apple (drawn as its icon) and Ctrl elsewhere; `Up`, `Down`, `Left` and
	`Right` are drawn as arrows. Any other key is printed as given.
-->
<script lang="ts">
	import { APPLE } from '#lib/shell.svelte.ts';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.ts';
	import Kbd from './Kbd.svelte';

	let { keys }: { keys: string[] } = $props();

	const ARROWS: Record<string, [IconName, string]> = {
		Up: ['arrow-up', 'Up arrow'],
		Down: ['arrow-down', 'Down arrow'],
		Left: ['arrow-left', 'Left arrow'],
		Right: ['arrow-right', 'Right arrow']
	};
</script>

<span class="shortcut">
	{#each keys as key, i (i)}
		<Kbd>
			{#if key === 'Mod' && APPLE}
				<Icon name="command" size={14} label="Command" />
			{:else if key === 'Mod'}
				Ctrl
			{:else if ARROWS[key]}
				<Icon name={ARROWS[key][0]} size={14} label={ARROWS[key][1]} />
			{:else}
				{key}
			{/if}
		</Kbd>
	{/each}
</span>

<style>
	.shortcut {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		flex-shrink: 0;
	}
</style>
