// The portal's keyboard map and the shell's overlays it opens.
//
// Everywhere: ⌘K (Ctrl+K off Apple) opens the command palette, ⌘1–5 go to the five
// destinations, ⌘\ collapses the sidebar, `/` focuses the current view's search field
// (or opens Search), Esc closes what is open or clears the field, and `?` shows the
// map. Keys without a modifier never fire while the reader is typing in a field.
//
// `overlays` is which of the shell's dialogs is open: the palette, the map, the mobile
// sheet. A screen that adds its own keys lists them in KEYMAP under its own heading, so
// `?` shows them.
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

/** The map `?` shows. */
export const KEYMAP: KeymapSection[] = [
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
