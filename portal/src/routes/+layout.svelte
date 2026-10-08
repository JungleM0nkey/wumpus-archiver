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
		goto,
		onNavigate,
		snapshot,
		type OnNavigate
	} from '$app/navigation';
	import CommandPalette from '#lib/components/shell/CommandPalette.svelte';
	import KeyboardMap from '#lib/components/shell/KeyboardMap.svelte';
	import Sidebar from '#lib/components/shell/Sidebar.svelte';
	import TabBar from '#lib/components/shell/TabBar.svelte';
	import TopBar from '#lib/components/shell/TopBar.svelte';
	import Dialog from '#lib/components/ui/Dialog.svelte';
	import {
		destinationShortcut,
		isPaletteShortcut,
		isTyping,
		overlays,
		runViewKey,
		searchInView
	} from '#lib/keyboard.svelte.ts';
	import {
		GUILD_PARAM,
		SCROLLER_ID,
		carryGuild,
		isRailShortcut,
		shell,
		sidebar,
		viewport,
		withGuild
	} from '#lib/shell.svelte.ts';

	let { children } = $props();

	let scroller: HTMLElement | undefined = $state();

	beforeNavigate(carryGuild);

	// Where focus was when the current navigation began.
	let focusAtStart: Element | null = null;
	beforeNavigate(() => {
		focusAtStart = document.activeElement;
	});

	/**
	 * Keep focus the reader moved into the shell while the navigation loaded. The router
	 * blurs whatever is focused as it swaps the screen, then moves focus to the page, as
	 * is right for the link that started the navigation. But a reader who has gone on to,
	 * say, the sidebar's search field is typing there: blurring it would drop their keys.
	 * The swap runs in this task, so its blur is undone before any key arrives.
	 */
	function keepShellFocus() {
		const focused = document.activeElement;
		if (!(focused instanceof HTMLElement) || focused === document.body) return;
		if (focused === focusAtStart || scroller?.contains(focused)) return;
		const refocus = () => focused.focus({ preventScroll: true });
		focused.addEventListener('blur', refocus, { once: true });
		setTimeout(() => focused.removeEventListener('blur', refocus));
	}

	// Going somewhere from the sheet closes it; the palette closes itself as it goes.
	afterNavigate(() => {
		overlays.sheet = false;
	});

	// The sheet is the narrow layout's; widening the window closes it.
	$effect(() => {
		if (!viewport.narrow) overlays.sheet = false;
	});

	/** Whether `navigation` changes the screen, not only its own search params. */
	function changesScreen(from: URL | undefined, to: URL | undefined): boolean {
		if (!from || !to) return true;
		return (
			from.pathname !== to.pathname ||
			from.searchParams.get(GUILD_PARAM) !== to.searchParams.get(GUILD_PARAM)
		);
	}

	/**
	 * The navigation whose screen is waiting on its cross-fade to swap in: the browser
	 * captures the old screen first, a frame or more later.
	 */
	let unswapped: OnNavigate | null = null;

	// Cross-fade the content between screens; the sidebar stays put.
	//
	// A screen waiting on its cross-fade still swaps in when the cross-fade gets there,
	// even if a newer navigation has begun since (back pressed right after a link, say).
	// So a navigation that starts meanwhile swaps in only after that one has: the screen
	// left showing is then the one the URL names.
	onNavigate((navigation: OnNavigate) => {
		const waiting = unswapped;
		const after = waiting ? waiting.complete.catch(() => {}) : undefined;
		if (!document.startViewTransition || !changesScreen(navigation.from?.url, navigation.to?.url)) {
			if (!after) {
				keepShellFocus();
				return;
			}
			return after.then(keepShellFocus);
		}
		unswapped = navigation;
		return new Promise<void>((resolve) => {
			const transition = document.startViewTransition(async () => {
				await after;
				if (unswapped === navigation) unswapped = null;
				keepShellFocus();
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

	// The keyboard map (keyboard.svelte.ts). A dialog handles its own Esc and Tab.
	function onKeydown(event: KeyboardEvent) {
		if (event.defaultPrevented) return;
		if (isRailShortcut(event)) {
			event.preventDefault();
			if (!viewport.narrow) sidebar.toggle();
			return;
		}
		if (isPaletteShortcut(event)) {
			event.preventDefault();
			overlays.palette = !overlays.palette;
			return;
		}
		const destination = destinationShortcut(event);
		if (destination) {
			event.preventDefault();
			overlays.closeAll();
			void goto(withGuild(destination.href));
			return;
		}
		if (overlays.any || event.metaKey || event.ctrlKey || event.altKey) return;

		const field = event.target;
		if (event.key === 'Escape' && isTyping(field)) {
			// Esc clears a text field, and leaves an empty one. A search field clears itself.
			if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
				if (!field.value) field.blur();
				else if (field.type !== 'search') {
					field.value = '';
					field.dispatchEvent(new Event('input', { bubbles: true }));
				}
			}
			return;
		}
		if (isTyping(event.target)) return;
		if (event.key === '?') {
			event.preventDefault();
			overlays.keymap = true;
		} else if (event.key === '/') {
			event.preventDefault();
			void searchInView();
		} else {
			runViewKey(event);
		}
	}
</script>

<svelte:head>
	<title>Wumpus Archiver</title>
</svelte:head>

<svelte:window onkeydown={onKeydown} />

<div class="shell" class:narrow={viewport.narrow}>
	{#if viewport.narrow}
		<TopBar />
	{:else}
		<Sidebar />
	{/if}
	<main id={SCROLLER_ID} class="scroller" bind:this={scroller}>
		{#key shell.guild?.id}
			{@render children()}
		{/key}
	</main>
	{#if viewport.narrow}
		<TabBar />
		<Dialog bind:open={overlays.sheet} label="Menu" placement="sheet" id="shell-sheet">
			<Sidebar sheet />
		</Dialog>
	{/if}
</div>

<CommandPalette />
<KeyboardMap />

<style>
	.shell {
		/* The height a sticky pane inside <main> fills to stay in view (shell.svelte.ts). */
		--shell-viewport-height: 100dvh;
		width: 100vw;
		height: 100dvh;
		display: flex;
		overflow: hidden;
	}

	/* Below 768px: the top bar, the content, the tab bar. */
	.shell.narrow {
		--shell-viewport-height: calc(
			100dvh - var(--size-topbar) - var(--size-tabbar) - env(safe-area-inset-bottom, 0px)
		);
		flex-direction: column;
	}

	.shell.narrow > :global(*:not(main)) {
		flex-shrink: 0;
	}

	.scroller {
		flex: 1;
		min-width: 0;
		min-height: 0;
		overflow-x: hidden;
		overflow-y: auto;
		view-transition-name: page;
	}
</style>
