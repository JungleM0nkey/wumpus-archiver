<!--
	A number that counts up from zero to `value` over 600ms (ease-out) when it first
	paints, then shows `value` as it is. Under reduced motion it shows `value` at once.
	It renders text only, formatted with toLocaleString, so its parent styles it.
-->
<script lang="ts">
	import { onMount } from 'svelte';

	let { value, duration = 600 }: { value: number; duration?: number } = $props();

	let counted = $state(0);
	let done = $state(false);

	onMount(() => {
		if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
			done = true;
			return;
		}
		const start = performance.now();
		let frame = requestAnimationFrame(function step(now) {
			const t = Math.min((now - start) / duration, 1);
			counted = Math.round(value * (1 - Math.pow(1 - t, 4)));
			if (t < 1) frame = requestAnimationFrame(step);
			else done = true;
		});
		return () => cancelAnimationFrame(frame);
	});
</script>

{(done ? value : counted).toLocaleString()}
