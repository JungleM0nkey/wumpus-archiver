<!-- The keyboard map `?` shows: the shell's keys and the screen's own (keyboard.svelte.ts), by where it works. -->
<script lang="ts">
	import { overlays, shortcuts } from '#lib/keyboard.svelte.ts';
	import Dialog from '../ui/Dialog.svelte';
	import IconButton from '../ui/IconButton.svelte';
	import Shortcut from '../ui/Shortcut.svelte';
</script>

<Dialog bind:open={overlays.keymap} label="Keyboard shortcuts" id="keyboard-map">
	<div class="keymap">
		<header class="head">
			<h2>Keyboard shortcuts</h2>
			<IconButton icon="x" label="Close" onclick={() => (overlays.keymap = false)} />
		</header>
		<div class="sections">
			{#each shortcuts.sections as section (section.heading)}
				<section>
					<h3>{section.heading}</h3>
					<dl>
						{#each section.bindings as binding (binding.does + binding.keys.join())}
							<div class="row">
								<dt>{binding.does}</dt>
								<dd><Shortcut keys={binding.keys} /></dd>
							</div>
						{/each}
					</dl>
				</section>
			{/each}
		</div>
	</div>
</Dialog>

<style>
	.keymap {
		display: flex;
		flex-direction: column;
		max-height: inherit;
	}

	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-3) var(--space-3) var(--space-3) var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
	}

	h2 {
		font: var(--type-heading-sm);
	}

	.sections {
		overflow-y: auto;
		padding: var(--space-2) var(--space-5) var(--space-5);
	}

	h3 {
		margin: var(--space-4) 0 var(--space-2);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-4);
		min-height: 32px;
		border-bottom: 1px solid var(--border-subtle);
	}

	.row:last-child {
		border-bottom: none;
	}

	dt {
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}
</style>
