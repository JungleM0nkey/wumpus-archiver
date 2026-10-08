<!--
	A row of tabs over panels the caller renders: a tablist whose indicator slides to the
	chosen tab (duration/small, standard easing; it jumps under reduced motion). Tab
	enters at the chosen tab, and the arrow keys, Home and End choose another. Each tab
	is `<id>-tab-<value>` and controls the panel `<id>-panel-<value>`, which the caller
	gives `role="tabpanel"` and `aria-labelledby` the tab. `onchange` runs only when the
	choice changes; the caller decides what `value` is (a URL param, say).
-->
<script lang="ts" generics="T extends string">
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.ts';

	let {
		tabs,
		value,
		id,
		label,
		onchange
	}: {
		tabs: { value: T; label: string; icon?: IconName }[];
		value: T;
		/** The prefix of the tabs' and panels' ids. */
		id: string;
		/** The tablist's accessible name. */
		label: string;
		onchange: (value: T) => void;
	} = $props();

	let buttons: HTMLButtonElement[] = $state([]);
	let list: HTMLElement | undefined = $state();
	let indicator = $state({ left: 0, width: 0 });
	/** No slide on first paint: the indicator starts under the chosen tab. */
	let placed = $state(false);

	const selected = $derived(Math.max(0, tabs.findIndex((t) => t.value === value)));

	// Follow the chosen tab, and its size as fonts load or the layout changes.
	$effect(() => {
		const button = buttons[selected];
		if (!button || !list) return;
		const place = () => {
			indicator = { left: button.offsetLeft, width: button.offsetWidth };
		};
		place();
		const observer = new ResizeObserver(place);
		observer.observe(button);
		observer.observe(list);
		requestAnimationFrame(() => (placed = true));
		return () => observer.disconnect();
	});

	const STEPS: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1 };

	function onkeydown(event: KeyboardEvent, index: number) {
		let target: number;
		if (event.key in STEPS) target = (index + STEPS[event.key] + tabs.length) % tabs.length;
		else if (event.key === 'Home') target = 0;
		else if (event.key === 'End') target = tabs.length - 1;
		else return;
		event.preventDefault();
		buttons[target]?.focus();
		choose(tabs[target].value);
	}

	function choose(next: T) {
		if (next !== value) onchange(next);
	}
</script>

<div class="tabs" role="tablist" aria-label={label} bind:this={list}>
	{#each tabs as tab, i (tab.value)}
		{@const chosen = i === selected}
		<button
			bind:this={buttons[i]}
			type="button"
			role="tab"
			id="{id}-tab-{tab.value}"
			aria-controls="{id}-panel-{tab.value}"
			aria-selected={chosen}
			tabindex={chosen ? 0 : -1}
			class="tab"
			class:chosen
			onclick={() => choose(tab.value)}
			onkeydown={(event) => onkeydown(event, i)}
		>
			{#if tab.icon}<Icon name={tab.icon} size={14} />{/if}
			{tab.label}
		</button>
	{/each}
	<span
		class="indicator"
		class:placed
		aria-hidden="true"
		style:translate="{indicator.left}px 0"
		style:width="{indicator.width}px"
	></span>
</div>

<style>
	.tabs {
		position: relative;
		display: flex;
		gap: var(--space-1);
	}

	.tab {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		height: 36px;
		padding: 0 var(--space-3);
		border-radius: var(--radius-sm) var(--radius-sm) 0 0;
		color: var(--text-tertiary);
		font: var(--type-label-md);
		white-space: nowrap;
		transition:
			color var(--duration-micro) var(--ease-out-quint),
			background-color var(--duration-micro) var(--ease-out-quint);
	}

	.tab:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.tab.chosen {
		color: var(--text-primary);
	}

	.indicator {
		position: absolute;
		left: 0;
		bottom: 0;
		height: 2px;
		border-radius: 1px;
		background: var(--accent);
		pointer-events: none;
	}

	.indicator.placed {
		transition:
			translate var(--duration-small) var(--ease-standard),
			width var(--duration-small) var(--ease-standard);
	}
</style>
