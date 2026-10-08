<!--
	A modal dialog: a native <dialog> opened with showModal(), so the page behind it is
	inert, drawn over an 8px backdrop blur. Tab and Shift+Tab stay inside it, Esc or a
	click on the backdrop closes it, and closing returns focus to what had it before.

	`placement` is where it sits: `center`, `top` (the command palette: a fixed top edge,
	so results changing below never move it), or `sheet` (a full-height panel from the
	left). It scales from 0.98, or a sheet slides in; under reduced motion both fade.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		open = $bindable(false),
		label,
		placement = 'center',
		initialFocus,
		id,
		children
	}: {
		open?: boolean;
		/** The dialog's accessible name. */
		label: string;
		placement?: 'center' | 'top' | 'sheet';
		/** A selector for the element that takes focus on opening; else the first focusable one. */
		initialFocus?: string;
		id?: string;
		children: Snippet;
	} = $props();

	let dialog: HTMLDialogElement | undefined = $state();
	let opener: HTMLElement | null = null;

	const FOCUSABLE =
		'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

	function focusables(): HTMLElement[] {
		if (!dialog) return [];
		return [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
			(el) => el.checkVisibility() && !el.closest('[inert]')
		);
	}

	$effect(() => {
		if (!dialog) return;
		if (open && !dialog.open) {
			opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
			dialog.showModal();
			const first = initialFocus ? dialog.querySelector<HTMLElement>(initialFocus) : focusables()[0];
			first?.focus();
		} else if (!open && dialog.open) {
			dialog.close();
			restoreFocus();
		}
	});

	/** Return focus to what had it, unless something else took it as the dialog closed. */
	function restoreFocus() {
		const active = document.activeElement;
		if (opener?.isConnected && (!active || active === document.body || dialog?.contains(active))) {
			opener.focus();
		}
		opener = null;
	}

	// The browser closed it (the close event is queued, so it may be open again by now).
	function onclose() {
		if (dialog?.open || !open) return;
		open = false;
		restoreFocus();
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.defaultPrevented) return;
		if (event.key === 'Escape') {
			// The dialog's own: Esc here closes this dialog, not something behind it.
			event.preventDefault();
			event.stopPropagation();
			open = false;
		} else if (event.key === 'Tab') {
			const items = focusables();
			if (items.length === 0) return event.preventDefault();
			const at = items.indexOf(document.activeElement as HTMLElement);
			const next = event.shiftKey
				? at <= 0
					? items.length - 1
					: at - 1
				: at === -1 || at === items.length - 1
					? 0
					: at + 1;
			event.preventDefault();
			items[next].focus();
		}
	}

	function onclick(event: MouseEvent) {
		// A click on the dialog element itself, not its content, is on the backdrop.
		if (event.target === dialog) open = false;
	}
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions (Esc, Tab and the backdrop click) -->
<!-- svelte-ignore a11y_click_events_have_key_events (Esc closes it from the keyboard) -->
<dialog
	bind:this={dialog}
	{id}
	class="dialog {placement}"
	aria-label={label}
	{onclose}
	{onkeydown}
	{onclick}
>
	{#if open}
		{@render children()}
	{/if}
</dialog>

<style>
	.dialog {
		margin: 0;
		padding: 0;
		border: 1px solid var(--border-default);
		background: var(--bg-overlay);
		color: var(--text-primary);
		box-shadow: var(--shadow-floating);
		overflow: hidden;
	}

	.dialog::backdrop {
		background: rgba(5, 5, 7, 0.55);
		backdrop-filter: blur(8px);
		animation: fade-in var(--duration-medium) var(--ease-out-quint);
	}

	.center,
	.top {
		left: 50%;
		translate: -50% 0;
		width: min(560px, calc(100vw - 2 * var(--space-4)));
		border-radius: var(--radius-lg);
		animation: scale-in var(--duration-medium) var(--ease-out-quint);
	}

	.center {
		top: 50%;
		translate: -50% -50%;
		max-height: calc(100dvh - 2 * var(--space-8));
	}

	/* A fixed top edge, so nothing that changes inside moves the dialog. */
	.top {
		top: min(12dvh, 96px);
		max-height: calc(100dvh - min(12dvh, 96px) - var(--space-4));
	}

	.sheet {
		top: 0;
		left: 0;
		width: min(300px, 85vw);
		height: 100dvh;
		max-height: none;
		border-width: 0 1px 0 0;
		border-radius: 0;
		background: var(--bg-surface);
		animation: sheet-in var(--duration-medium) var(--ease-out-quint);
	}
</style>
