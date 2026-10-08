<script lang="ts">
	// The portal's shell: the sidebar, and <main>, the one element page content scrolls
	// in. Routes reach both through #lib/shell.svelte.ts, which documents what they may
	// rely on: the selected guild, and the scroll container.
	//
	// The route remounts whenever the selected guild changes, so every screen re-reads
	// its data for the new guild. Content cross-fades between screens (a view transition
	// on <main>), and each history entry keeps its scroll position for back/forward.

	// The portal self-hosts its two typefaces, so it loads no fonts from the network.
	import '@fontsource-variable/instrument-sans';
	import '@fontsource-variable/jetbrains-mono';
	import '../lib/styles/global.css';
	import {
		afterNavigate,
		beforeNavigate,
		onNavigate,
		snapshot,
		type OnNavigate
	} from '$app/navigation';
	import Sidebar from '#lib/components/shell/Sidebar.svelte';
	import {
		GUILD_PARAM,
		SCROLLER_ID,
		carryGuild,
		isRailShortcut,
		shell,
		sidebar
	} from '#lib/shell.svelte.ts';

	let { children } = $props();

	let scroller: HTMLElement | undefined = $state();

	beforeNavigate(carryGuild);

	/** Whether `navigation` changes the screen, not only its own search params. */
	function changesScreen(from: URL | undefined, to: URL | undefined): boolean {
		if (!from || !to) return true;
		return (
			from.pathname !== to.pathname ||
			from.searchParams.get(GUILD_PARAM) !== to.searchParams.get(GUILD_PARAM)
		);
	}

	// Cross-fade the content between screens; the sidebar stays put.
	onNavigate((navigation: OnNavigate) => {
		if (!document.startViewTransition) return;
		if (!changesScreen(navigation.from?.url, navigation.to?.url)) return;
		return new Promise<void>((resolve) => {
			const transition = document.startViewTransition(async () => {
				resolve();
				await navigation.complete.catch(() => {});
			});
			// A transition skipped by a newer navigation rejects these; nothing to do.
			transition.ready.catch(() => {});
			transition.finished.catch(() => {});
		});
	});

	// A new screen starts at the top; back/forward restore where it was (below).
	afterNavigate((navigation) => {
		if (navigation.type === 'enter' || navigation.type === 'popstate') return;
		if (!changesScreen(navigation.from?.url, navigation.to?.url)) return;
		stopRestoring();
		if (scroller) scroller.scrollTop = 0;
	});

	let restoring: number | undefined;

	function stopRestoring() {
		if (restoring !== undefined) cancelAnimationFrame(restoring);
		restoring = undefined;
	}

	/**
	 * Scroll back to `y`, and hold it there for 3 s, or until the reader scrolls. The
	 * route is usually still loading what made it that tall: reaching `y` early proves
	 * nothing, as the content arriving later can still clamp the position (a skeleton
	 * swapped for something shorter) or shift it (scroll anchoring, when content grows
	 * above the view). So each frame puts it back where it moved.
	 */
	function restoreScroll(y: number) {
		stopRestoring();
		const until = performance.now() + 3_000;
		const step = () => {
			restoring = undefined;
			if (!scroller) return;
			if (Math.abs(scroller.scrollTop - y) > 1) scroller.scrollTop = y;
			if (performance.now() < until) restoring = requestAnimationFrame(step);
		};
		step();
	}

	// The reader taking the scroll back stops a restore: anywhere on the page, as keys
	// scroll <main> while focus is outside it.
	$effect(() => {
		const events = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const;
		const options = { capture: true, passive: true };
		for (const type of events) window.addEventListener(type, stopRestoring, options);
		return () => {
			for (const type of events) window.removeEventListener(type, stopRestoring, options);
		};
	});

	snapshot<number>({
		id: 'shell-scroll',
		capture: () => scroller?.scrollTop ?? 0,
		restore: restoreScroll
	});

	function onKeydown(event: KeyboardEvent) {
		if (isRailShortcut(event)) {
			event.preventDefault();
			sidebar.toggle();
		}
	}
</script>

<svelte:head>
	<title>Wumpus Archiver</title>
</svelte:head>

<svelte:window onkeydown={onKeydown} />

<div class="shell">
	<Sidebar />
	<main id={SCROLLER_ID} class="scroller" bind:this={scroller}>
		{#key shell.guild?.id}
			{@render children()}
		{/key}
	</main>
</div>

<style>
	.shell {
		/* The height a sticky pane inside <main> fills to stay in view (shell.svelte.ts). */
		--shell-viewport-height: 100dvh;
		width: 100vw;
		height: 100dvh;
		display: flex;
		overflow: hidden;
	}

	.scroller {
		flex: 1;
		min-width: 0;
		overflow-x: hidden;
		overflow-y: auto;
		view-transition-name: page;
	}
</style>
