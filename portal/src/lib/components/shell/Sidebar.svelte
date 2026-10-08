<!--
	The shell's sidebar: the brand, the guild switcher, a search field, the five
	destinations and the archive-status card. It collapses to a 64px icon rail with
	Command- or Control-backslash (shell.svelte.ts keeps the choice), where labels fade
	out and each item shows its name as a tooltip. Below 768px the layout opens it as a
	sheet (`sheet`): always expanded, with a button that closes it.
-->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { MOD_ARIA, overlays } from '#lib/keyboard.svelte.ts';
	import {
		DESTINATIONS,
		RAIL_KEYSHORTCUTS,
		RAIL_SHORTCUT,
		sidebar,
		withGuild
	} from '#lib/shell.svelte.ts';
	import Icon from '../ui/Icon.svelte';
	import IconButton from '../ui/IconButton.svelte';
	import Shortcut from '../ui/Shortcut.svelte';
	import { tooltip } from '../ui/tooltip.ts';
	import ArchiveStatus from './ArchiveStatus.svelte';
	import GuildSwitcher from './GuildSwitcher.svelte';

	let { sheet = false }: { sheet?: boolean } = $props();

	const rail = $derived(sidebar.rail && !sheet);
	let query = $state('');

	function search(event: SubmitEvent) {
		event.preventDefault();
		const q = query.trim();
		query = '';
		void goto(withGuild(q ? `/search?q=${encodeURIComponent(q)}` : '/search'));
	}
</script>

<aside class="sidebar" class:rail class:sheet aria-label="Sidebar">
	<div class="brand-row">
		<a href={withGuild('/')} class="brand" aria-label="Wumpus Archiver" use:tooltip={{ text: 'Wumpus Archiver', enabled: rail }}>
			<span class="brand-mark"><Icon name="archive" size={18} /></span>
			<span class="label brand-text">wumpus<span class="brand-accent">.archive</span></span>
		</a>
		{#if sheet}
			<IconButton icon="x" label="Close menu" onclick={() => (overlays.sheet = false)} />
		{/if}
	</div>

	<div class="section">
		<GuildSwitcher {rail} anchored={sheet} />
	</div>

	<form class="section search" role="search" onsubmit={search}>
		<button
			type="submit"
			class="search-icon"
			aria-label="Search"
			tabindex={rail ? 0 : -1}
			use:tooltip={{ text: 'Search', enabled: rail }}
		>
			<Icon name="search" />
		</button>
		<input
			class="label search-input"
			type="search"
			bind:value={query}
			placeholder="Search messages"
			aria-label="Search messages"
			inert={rail}
		/>
		<!-- The sheet's top bar has its own way into the palette. -->
		{#if !sheet}
			<button
				type="button"
				class="label palette-key"
				aria-label="Open the command palette"
				aria-keyshortcuts="{MOD_ARIA}+K"
				inert={rail}
				onclick={() => (overlays.palette = true)}
			>
				<Shortcut keys={['Mod', 'K']} />
			</button>
		{/if}
	</form>

	<nav class="nav" aria-label="Destinations">
		{#each DESTINATIONS as destination (destination.href)}
			{@const active = destination.owns(page.url.pathname)}
			<a
				href={withGuild(destination.href)}
				class="nav-item"
				class:active
				aria-current={active ? 'page' : undefined}
				use:tooltip={{ text: destination.label, enabled: rail }}
			>
				<Icon name={destination.icon} size={18} />
				<span class="label">{destination.label}</span>
			</a>
		{/each}
	</nav>

	<div class="footer">
		<ArchiveStatus {rail} />
		<div class="footer-row">
			{#if !sheet}
				<IconButton
					icon={sidebar.rail ? 'panel-left-open' : 'panel-left-close'}
					label="{sidebar.rail ? 'Expand' : 'Collapse'} sidebar ({RAIL_SHORTCUT})"
					aria-keyshortcuts={RAIL_KEYSHORTCUTS}
					aria-expanded={!sidebar.rail}
					onclick={sidebar.toggle}
				/>
			{/if}
			<span class="label footer-end" inert={rail}>
				<IconButton
					icon="keyboard"
					label="Keyboard shortcuts (?)"
					aria-keyshortcuts="?"
					onclick={() => (overlays.keymap = true)}
				/>
				<span class="version mono">v{__PORTAL_VERSION__}</span>
			</span>
		</div>
	</div>
</aside>

<style>
	.sidebar {
		width: var(--size-sidebar);
		height: 100%;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-3);
		background: var(--bg-surface);
		border-right: 1px solid var(--border-subtle);
		overflow: hidden;
		transition: width var(--duration-large) var(--ease-in-out);
	}

	/* In the mobile sheet it fills the sheet, which draws the edge. */
	.sidebar.sheet {
		width: 100%;
		border-right: none;
		background: none;
	}

	.sidebar.sheet .brand-row {
		justify-content: space-between;
	}

	/* The sheet's guild list opens under its trigger (GuildSwitcher's `anchored`). */
	.section {
		position: relative;
	}

	.sidebar.rail {
		width: var(--size-rail);
	}

	/*
	 * Labels fade out in the first 120 ms of a collapse, then the width closes over them;
	 * on expanding they fade back in as the width finishes opening.
	 */
	.sidebar :global(.label) {
		white-space: nowrap;
		transition: opacity var(--duration-micro) var(--ease-out-quint)
			calc(var(--duration-large) - var(--duration-micro));
	}

	.sidebar.rail :global(.label) {
		opacity: 0;
		pointer-events: none;
		transition-delay: 0ms;
	}

	.brand-row {
		display: flex;
		align-items: center;
		height: 40px;
		margin-bottom: var(--space-1);
	}

	.brand {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding-left: 6px;
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		font: var(--type-heading-sm);
	}

	.brand:hover {
		color: var(--text-primary);
	}

	.brand-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		background: var(--accent-muted);
		color: var(--accent);
	}

	.brand-accent {
		color: var(--text-secondary);
		font-weight: 500;
	}

	.search {
		display: flex;
		align-items: center;
		height: 36px;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		background: var(--bg-canvas);
		color: var(--text-tertiary);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.search:focus-within {
		border-color: var(--border-strong);
	}

	.rail .search {
		border-color: transparent;
		background: none;
	}

	.search-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		/* The icon's centre lines up with the nav icons' on the rail. */
		width: 38px;
		height: 34px;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		color: inherit;
	}

	.rail .search-icon:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.search-input {
		flex: 1;
		min-width: 0;
		height: 100%;
		padding-right: var(--space-2);
		font: var(--type-body-sm);
		color: var(--text-primary);
		outline: none;
	}

	.search-input::placeholder {
		color: var(--text-tertiary);
	}

	.palette-key {
		display: inline-flex;
		align-items: center;
		height: 100%;
		padding: 0 6px 0 var(--space-1);
		border-radius: var(--radius-sm);
	}

	.palette-key:hover :global(.kbd) {
		color: var(--text-primary);
		border-color: var(--border-strong);
	}

	.nav {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
		margin-top: var(--space-2);
		overflow-x: hidden;
		overflow-y: auto;
	}

	.nav-item {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		height: 36px;
		flex-shrink: 0;
		/* (40px rail item − 18px icon) / 2: the icon sits at the rail's centre. */
		padding: 0 11px;
		border-radius: var(--radius-sm);
		font: var(--type-label-md);
		color: var(--text-secondary);
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.nav-item:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.nav-item.active {
		color: var(--text-primary);
		background: var(--bg-active);
	}

	.nav-item.active :global(.icon) {
		color: var(--accent);
	}

	.footer {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.footer-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
		/* The toggle's centre lines up with the nav icons' on the rail. */
		padding-left: 4px;
		min-height: 32px;
	}

	.footer-end {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		margin-left: auto;
	}

	.version {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		padding: 3px 8px;
		border-radius: var(--radius-xs);
		background: var(--bg-raised);
		border: 1px solid var(--border-subtle);
	}
</style>
