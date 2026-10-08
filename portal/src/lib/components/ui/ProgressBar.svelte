<!--
	A progress bar: a fill `value` percent across its track, or, with no value, a fill
	sweeping across it for work whose end is not known. Under reduced motion the sweep
	becomes a pulse (global.css).
-->
<script lang="ts">
	let {
		value = null,
		label,
		tone = 'accent',
		size = 'md'
	}: {
		/** Percent done, 0 to 100; null while it is not known. */
		value?: number | null;
		/** What the bar measures, for assistive technology. */
		label: string;
		tone?: 'accent' | 'success' | 'danger' | 'warning' | 'neutral';
		size?: 'sm' | 'md';
	} = $props();

	const percent = $derived(value === null ? null : Math.max(0, Math.min(100, value)));
</script>

<div
	class="track {tone} {size}"
	role="progressbar"
	aria-label={label}
	aria-valuemin={percent === null ? undefined : 0}
	aria-valuemax={percent === null ? undefined : 100}
	aria-valuenow={percent === null ? undefined : Math.round(percent)}
>
	{#if percent === null}
		<div class="fill sweep"></div>
	{:else}
		<div class="fill" style:width="{percent}%"></div>
	{/if}
</div>

<style>
	.track {
		--tone: var(--accent);
		width: 100%;
		background: var(--bg-inset);
		border-radius: var(--radius-full);
		overflow: hidden;
	}

	.sm {
		height: 4px;
	}
	.md {
		height: 6px;
	}

	.success {
		--tone: var(--success);
	}
	.danger {
		--tone: var(--danger);
	}
	.warning {
		--tone: var(--warning);
	}
	.neutral {
		--tone: var(--text-tertiary);
	}

	.fill {
		height: 100%;
		background: var(--tone);
		border-radius: var(--radius-full);
		transition: width var(--duration-medium) var(--ease-out-quint);
	}

	.sweep {
		width: 40%;
		animation: sweep 1.8s var(--ease-in-out) infinite;
	}
</style>
