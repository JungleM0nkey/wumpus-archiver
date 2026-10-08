<!--
	The narrow layout's top bar: the menu button that opens the sidebar as a sheet, the
	selected guild, and the button that opens the command palette.
-->
<script lang="ts">
	import { overlays } from '#lib/keyboard.svelte.ts';
	import { shell, withGuild } from '#lib/shell.svelte.ts';
	import Icon from '../ui/Icon.svelte';
	import IconButton from '../ui/IconButton.svelte';
</script>

<header class="top-bar">
	<IconButton
		icon="menu"
		size="lg"
		label="Open menu"
		aria-haspopup="dialog"
		aria-expanded={overlays.sheet}
		aria-controls="shell-sheet"
		onclick={() => (overlays.sheet = true)}
	/>
	<a href={withGuild('/')} class="title" aria-label="Wumpus Archiver: Overview">
		<span class="brand-mark"><Icon name="archive" size={16} /></span>
		<span class="name truncate">{shell.guild?.name ?? 'Wumpus Archiver'}</span>
	</a>
	<IconButton
		icon="search"
		size="lg"
		label="Search or jump to"
		aria-haspopup="dialog"
		aria-expanded={overlays.palette}
		aria-controls="command-palette"
		onclick={() => (overlays.palette = true)}
	/>
</header>

<style>
	.top-bar {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		height: var(--size-topbar);
		padding: 0 var(--space-3);
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
	}

	.title {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		color: var(--text-primary);
		font: var(--type-heading-sm);
	}

	.title:hover {
		color: var(--text-primary);
	}

	.brand-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		flex-shrink: 0;
		border-radius: var(--radius-xs);
		background: var(--accent-muted);
		color: var(--accent);
	}
</style>
