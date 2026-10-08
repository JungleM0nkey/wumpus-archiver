<!--
	The sidebar's guild switcher: the selected guild, and a list of every archived guild
	that re-scopes the current screen to the one picked (shell.svelte.ts). On the rail it
	is the guild's avatar alone, and the list opens beside it.
-->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { guildSwitchHref, shell } from '#lib/shell.svelte.ts';
	import type { Guild } from '#lib/types.ts';
	import Icon from '../ui/Icon.svelte';
	import { tooltip } from '../ui/tooltip.ts';

	let { rail = false }: { rail?: boolean } = $props();

	const listId = 'guild-switcher-list';
	let open = $state(false);
	let active = $state(0);
	let trigger: HTMLButtonElement | undefined = $state();
	let list: HTMLElement | undefined = $state();
	let position = $state({ top: 0, left: 0, width: 0 });

	const current = $derived(shell.guild);

	function initial(guild: Guild): string {
		return (guild.name.trim()[0] ?? '?').toUpperCase();
	}

	function count(n: number): string {
		return `${n.toLocaleString()} message${n === 1 ? '' : 's'}`;
	}

	function place() {
		if (!trigger) return;
		const rect = trigger.getBoundingClientRect();
		position = rail
			? { top: rect.top, left: rect.right + 8, width: 248 }
			: { top: rect.bottom + 4, left: rect.left, width: Math.max(rect.width, 216) };
	}

	async function openList() {
		place();
		active = Math.max(0, shell.guilds.findIndex((g) => g.id === current?.id));
		open = true;
		await Promise.resolve();
		list?.focus();
	}

	function close(refocus = true) {
		open = false;
		if (refocus) trigger?.focus();
	}

	function choose(guild: Guild) {
		close();
		if (guild.id !== current?.id) void goto(guildSwitchHref(guild.id));
	}

	function onListKeydown(event: KeyboardEvent) {
		const last = shell.guilds.length - 1;
		switch (event.key) {
			case 'ArrowDown':
				active = Math.min(last, active + 1);
				break;
			case 'ArrowUp':
				active = Math.max(0, active - 1);
				break;
			case 'Home':
				active = 0;
				break;
			case 'End':
				active = last;
				break;
			case 'Enter':
			case ' ':
				choose(shell.guilds[active]);
				break;
			case 'Escape':
				close();
				break;
			case 'Tab':
				close(false);
				return;
			default:
				return;
		}
		event.preventDefault();
	}

	function onWindowPointerdown(event: PointerEvent) {
		if (!open) return;
		const target = event.target as Node;
		if (!list?.contains(target) && !trigger?.contains(target)) close(false);
	}
</script>

<svelte:window onpointerdown={onWindowPointerdown} onresize={() => open && place()} />

{#if current}
	<button
		bind:this={trigger}
		class="trigger"
		type="button"
		aria-haspopup="listbox"
		aria-expanded={open}
		aria-controls={open ? listId : undefined}
		aria-label="Guild: {current.name}"
		onclick={() => (open ? close() : openList())}
		use:tooltip={{ text: current.name, enabled: rail && !open }}
	>
		{@render avatar(current)}
		<span class="label text">
			<span class="name truncate">{current.name}</span>
			<span class="meta mono">{count(current.message_count)}</span>
		</span>
		<span class="label chevron"><Icon name="chevrons-up-down" /></span>
	</button>

	{#if open}
		<div
			bind:this={list}
			id={listId}
			class="list"
			role="listbox"
			aria-label="Guilds"
			aria-activedescendant="guild-option-{active}"
			tabindex="-1"
			style:top="{position.top}px"
			style:left="{position.left}px"
			style:width="{position.width}px"
			onkeydown={onListKeydown}
		>
			{#each shell.guilds as guild, i (guild.id)}
				{@const selected = guild.id === current.id}
				<!-- svelte-ignore a11y_click_events_have_key_events (the listbox handles keys) -->
				<div
					id="guild-option-{i}"
					class="option"
					class:active={i === active}
					role="option"
					tabindex="-1"
					aria-selected={selected}
					onclick={() => choose(guild)}
					onpointermove={() => (active = i)}
				>
					{@render avatar(guild)}
					<span class="text">
						<span class="name truncate">{guild.name}</span>
						<span class="meta mono">{count(guild.message_count)}</span>
					</span>
					{#if selected}<Icon name="check" />{/if}
				</div>
			{/each}
		</div>
	{/if}
{/if}

{#snippet avatar(guild: Guild)}
	{#if guild.icon_url}
		<img class="avatar" src={guild.icon_url} alt="" />
	{:else}
		<span class="avatar fallback" aria-hidden="true">{initial(guild)}</span>
	{/if}
{/snippet}

<style>
	.trigger {
		width: 100%;
		display: flex;
		align-items: center;
		gap: var(--space-3);
		height: 48px;
		/* On the rail the avatar's centre lines up with the nav icons'. */
		padding: 0 var(--space-2) 0 5px;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		background: var(--bg-raised);
		text-align: left;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint);
	}

	.trigger:hover,
	.trigger[aria-expanded='true'] {
		background: var(--bg-overlay);
		border-color: var(--border-default);
	}

	.avatar {
		width: 28px;
		height: 28px;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}

	.avatar.fallback {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		background: var(--accent-muted);
		color: var(--accent);
		font: var(--type-heading-sm);
	}

	.text {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.name {
		font: var(--type-label-md);
		color: var(--text-primary);
	}

	.meta {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.chevron {
		display: inline-flex;
		color: var(--text-tertiary);
	}

	.list {
		position: fixed;
		z-index: 200;
		display: flex;
		flex-direction: column;
		gap: 2px;
		max-height: min(360px, calc(100dvh - 32px));
		overflow-y: auto;
		padding: var(--space-1);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		background: var(--bg-overlay);
		box-shadow: var(--shadow-floating);
		transform-origin: top left;
		animation: scale-in var(--duration-medium) var(--ease-out-quint);
	}

	.option {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: 6px;
		border-radius: var(--radius-sm);
		cursor: pointer;
	}

	.option :global(.icon) {
		color: var(--accent);
	}

	.option.active {
		background: var(--bg-hover);
	}
</style>
