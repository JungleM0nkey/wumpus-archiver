// The portal's keyboard map and the shell's overlays it opens.
//
// Everywhere: ⌘K (Ctrl+K off Apple) opens the command palette, ⌘1–5 go to the five
// destinations, ⌘\ collapses the sidebar, `/` focuses the current view's search field
// (the first `type="search"` field in <main>, or one marked `data-view-search`) or else
// opens Search, Esc closes what is open or clears the field, and `?` shows the map. Keys without a modifier never fire while the reader is typing in a field.
//
// `overlays` is which of the shell's dialogs is open: the palette, the map, the mobile
// sheet.
//
// A screen's own keys go through this registry too: `useViewKeys` registers them while
// the screen is mounted, the shell's one keydown handler runs them (never while typing,
// with a modifier, or while a dialog is open), and `?` lists them under the screen's
// heading. Browse's reader registers J, K and "G then L" this way.
import { untrack } from 'svelte';
import { goto } from '$app/navigation';
import { APPLE, DESTINATIONS, withGuild } from './shell.svelte';

/** The modifier key as the keyboard labels it. */
export const MOD = APPLE ? '⌘' : 'Ctrl';

/** The modifier key's name for aria-keyshortcuts. */
export const MOD_ARIA = APPLE ? 'Meta' : 'Control';

/** The palette's keys as the keyboard labels them. */
export const PALETTE_SHORTCUT = APPLE ? '⌘K' : 'Ctrl+K';

let palette = $state(false);
let keymap = $state(false);
let sheet = $state(false);

/** Which of the shell's dialogs is open. Opening one closes the others. */
export const overlays = {
	get palette(): boolean {
		return palette;
	},
	set palette(open: boolean) {
		if (open) keymap = sheet = false;
		palette = open;
	},
	get keymap(): boolean {
		return keymap;
	},
	set keymap(open: boolean) {
		if (open) palette = sheet = false;
		keymap = open;
	},
	get sheet(): boolean {
		return sheet;
	},
	set sheet(open: boolean) {
		if (open) palette = keymap = false;
		sheet = open;
	},
	get any(): boolean {
		return palette || keymap || sheet;
	},
	closeAll(): void {
		palette = keymap = sheet = false;
	}
};

export interface KeyBinding {
	/**
	 * The keys, each drawn as one Kbd by Shortcut.svelte: `Mod` is Command on Apple and
	 * Ctrl elsewhere, `Up`/`Down`/`Left`/`Right` are the arrows, anything else is printed.
	 */
	keys: string[];
	/** What they do. */
	does: string;
}

export interface KeymapSection {
	heading: string;
	bindings: KeyBinding[];
}

/** The shell's own keys, which work on every screen. */
const SHELL_KEYS: KeymapSection[] = [
	{
		heading: 'Everywhere',
		bindings: [
			{ keys: ['Mod', 'K'], does: 'Open the command palette' },
			...DESTINATIONS.map((d, i) => ({ keys: ['Mod', String(i + 1)], does: `Go to ${d.label}` })),
			{ keys: ['Mod', '\\'], does: 'Collapse or expand the sidebar' },
			{ keys: ['/'], does: 'Search in this view' },
			{ keys: ['Esc'], does: 'Close or clear' },
			{ keys: ['?'], does: 'Show this map' }
		]
	},
	{
		heading: 'Command palette',
		bindings: [
			{ keys: ['Up', 'Down'], does: 'Move between results' },
			{ keys: ['Enter'], does: 'Open the result' }
		]
	},
	{
		heading: 'Lightbox',
		bindings: [
			{ keys: ['Left', 'Right'], does: 'Previous or next attachment' },
			{ keys: ['Esc'], does: 'Close' }
		]
	}
];

/** A key of a screen's own, or a chord of two pressed one after the other. */
export interface ViewBinding extends KeyBinding {
	/** The keys pressed, as lowercase `KeyboardEvent.key`s: two for a chord ("G then L"). */
	press: [string] | [string, string];
	run: () => void;
	/** Whether the key applies right now, such as only on one tab. */
	when?: () => boolean;
}

export interface ViewKeys {
	/** Where they work, as `?` heads them: "Browse", say. */
	heading: string;
	bindings: ViewBinding[];
}

/** How long after a chord's first key its second still completes it. */
export const CHORD_MS = 1500;

let viewKeys = $state.raw<ViewKeys[]>([]);

/** Every key `?` lists: the shell's, then those of the screen on show. */
export const shortcuts = {
	get sections(): KeymapSection[] {
		return [...SHELL_KEYS, ...viewKeys];
	}
};

/**
 * Register a screen's own keys while it is mounted; call it during the component's
 * initialisation. The shell runs them, and `?` lists them.
 */
export function useViewKeys(keys: ViewKeys): void {
	$effect(() => {
		untrack(() => (viewKeys = [...viewKeys, keys]));
		return () => {
			viewKeys = untrack(() => viewKeys.filter((k) => k !== keys));
		};
	});
}

/** A chord's first key, while its second may still follow. */
let chordStart: { key: string; at: number } | null = null;

/**
 * Run the screen's key that `event` presses, if one applies. The shell calls it only for
 * a key without a modifier (Shift aside), outside a field, with no dialog open.
 */
export function runViewKey(event: KeyboardEvent): boolean {
	const key = event.key.toLowerCase();
	const bindings = viewKeys.flatMap((k) => k.bindings).filter((b) => b.when?.() ?? true);
	const first = chordStart && performance.now() - chordStart.at < CHORD_MS ? chordStart.key : null;
	chordStart = null;
	if (first) {
		const chord = bindings.find((b) => b.press.length === 2 && b.press[0] === first && b.press[1] === key);
		if (chord) {
			event.preventDefault();
			chord.run();
			return true;
		}
	}
	if (event.shiftKey) return false;
	if (bindings.some((b) => b.press.length === 2 && b.press[0] === key)) {
		chordStart = { key, at: performance.now() };
		return true;
	}
	const single = bindings.find((b) => b.press.length === 1 && b.press[0] === key);
	if (!single) return false;
	event.preventDefault();
	single.run();
	return true;
}

/** Whether `target` takes typed text, so a key without a modifier belongs to it. */
export function isTyping(target: EventTarget | null): boolean {
	if (!(target instanceof HTMLElement)) return false;
	if (target.isContentEditable) return true;
	if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
	if (!(target instanceof HTMLInputElement)) return false;
	return !['button', 'checkbox', 'color', 'file', 'image', 'radio', 'range', 'reset', 'submit'].includes(
		target.type
	);
}

/** Whether `event` holds Command (Apple) or Control and no other modifier. */
function withMod(event: KeyboardEvent): boolean {
	return (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey;
}

/** Whether `event` is the palette's shortcut. */
export function isPaletteShortcut(event: KeyboardEvent): boolean {
	return withMod(event) && event.key.toLowerCase() === 'k';
}

/** The destination ⌘1–5 in `event` goes to, if it is one. */
export function destinationShortcut(event: KeyboardEvent): (typeof DESTINATIONS)[number] | null {
	if (!withMod(event)) return null;
	const digit = /^Digit([1-9])$/.exec(event.code)?.[1] ?? (/^[1-9]$/.test(event.key) ? event.key : null);
	return digit ? (DESTINATIONS[Number(digit) - 1] ?? null) : null;
}

/** The fields a view searches with: the first one in the shell's <main> is `/`'s. */
const VIEW_SEARCH = 'input[type="search"], [role="searchbox"], [data-view-search]';

function viewSearch(): HTMLElement | null {
	const main = document.querySelector('main');
	const fields = main ? [...main.querySelectorAll<HTMLElement>(VIEW_SEARCH)] : [];
	return fields.find((field) => field.checkVisibility() && !field.closest('[inert]')) ?? null;
}

function focusField(field: HTMLElement) {
	field.focus();
	if (field instanceof HTMLInputElement) field.select();
}

/** `/`: focus the current view's search field, or open Search and focus its field. */
export async function searchInView(): Promise<void> {
	const field = viewSearch();
	if (field) return focusField(field);
	await goto(withGuild('/search'));
	// The Search screen renders its field once it mounts.
	const until = performance.now() + 2_000;
	await new Promise<void>((resolve) => {
		const look = () => {
			const found = viewSearch();
			if (found) focusField(found);
			if (found || performance.now() > until) resolve();
			else requestAnimationFrame(look);
		};
		look();
	});
}
