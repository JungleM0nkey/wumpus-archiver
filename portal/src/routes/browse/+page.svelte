<script lang="ts">
	// Browse with no channel named opens the guild's most active channel, in place of
	// this history entry. Below 768px it shows the channel pane alone (the layout) and
	// waits for a pick.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { getBrowseGuild } from '#lib/browse.ts';
	import { openingChannel } from '#lib/channels.ts';
	import { channelHref } from '#lib/routes.ts';
	import { withGuild } from '#lib/shell.svelte.ts';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import MessageSkeleton from '#lib/components/MessageSkeleton.svelte';

	const browse = getBrowseGuild();
	let empty = $state(false);
	let failed = $state(false);

	onMount(async () => {
		if (!(await browse.ready)) return;
		// The pane says why the guild could not be read.
		if (!browse.detail) {
			failed = true;
			return;
		}
		const channel = openingChannel(browse.detail.channels);
		if (!channel) {
			empty = true;
			return;
		}
		if (!matchMedia('(min-width: 768px)').matches) return;
		// withGuild here, not the shell's carrying: that would lose replaceState.
		await goto(withGuild(channelHref(channel.id)), { replaceState: true });
	});
</script>

<div class="placeholder">
	{#if empty}
		<EmptyState icon="inbox" title="No channels to read" description="This guild has no archived text channels." />
	{:else if !failed}
		<MessageSkeleton />
	{/if}
</div>

<style>
	.placeholder {
		flex: 1;
		display: flex;
		flex-direction: column;
		justify-content: center;
		width: 100%;
		max-width: var(--size-reader-max);
		margin: 0 auto;
		padding: var(--space-6);
	}
</style>
