<!--
	One choice of a few, side by side: a sort, a view. It is a radio group, so Tab enters
	it at the chosen option and the arrow keys (Home, End) move the choice. `onchange`
	runs only when the choice changes.
-->
<script lang="ts" generics="T extends string">
	let {
		options,
		value = $bindable(),
		label,
		onchange
	}: {
		options: { value: T; label: string }[];
		value: T;
		/** The group's accessible name, such as "Sort by". */
		label: string;
		onchange?: (value: T) => void;
	} = $props();

	let buttons: HTMLButtonElement[] = $state([]);

	function choose(next: T) {
		if (next === value) return;
		value = next;
		onchange?.(next);
	}

	const STEPS: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

	function onkeydown(event: KeyboardEvent, index: number) {
		let target: number;
		if (event.key in STEPS) target = (index + STEPS[event.key] + options.length) % options.length;
		else if (event.key === 'Home') target = 0;
		else if (event.key === 'End') target = options.length - 1;
		else return;
		event.preventDefault();
		buttons[target]?.focus();
		choose(options[target].value);
	}
</script>

<div class="segmented" role="radiogroup" aria-label={label}>
	{#each options as option, i (option.value)}
		{@const checked = option.value === value}
		<button
			bind:this={buttons[i]}
			type="button"
			role="radio"
			aria-checked={checked}
			tabindex={checked ? 0 : -1}
			class="segment"
			class:checked
			onclick={() => choose(option.value)}
			onkeydown={(event) => onkeydown(event, i)}
		>
			{option.label}
		</button>
	{/each}
</div>

<style>
	.segmented {
		display: inline-flex;
		gap: 2px;
		padding: 2px;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		background: var(--bg-surface);
	}

	.segment {
		height: 28px;
		padding: 0 var(--space-3);
		border-radius: var(--radius-xs);
		color: var(--text-secondary);
		font: var(--type-label-sm);
		white-space: nowrap;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.segment:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.segment.checked {
		background: var(--bg-overlay);
		color: var(--text-primary);
		box-shadow: inset 0 0 0 1px var(--border-default);
	}
</style>
