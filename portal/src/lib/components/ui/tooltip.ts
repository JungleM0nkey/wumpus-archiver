// A tooltip for an element whose label is hidden, such as an item on the sidebar's
// icon rail: `use:tooltip={{ text, enabled }}`. It appears beside the element after
// TOOLTIP_DELAY_MS of hover or keyboard focus and goes on leave, blur, Escape or click.
// It is drawn on <body> (styled by `.tooltip` in global.css) so no overflow clips it.
import type { Action } from 'svelte/action';

/** The proposal's rail tooltips wait 400 ms (docs/UI_UX_PROPOSAL.md section 5). */
export const TOOLTIP_DELAY_MS = 400;

export interface TooltipOptions {
	text: string;
	/** Whether the tooltip shows at all, e.g. only while the sidebar is a rail. */
	enabled?: boolean;
}

let next = 0;

export const tooltip: Action<HTMLElement, TooltipOptions> = (node, initial) => {
	let options = initial;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let tip: HTMLElement | null = null;
	const id = `tooltip-${++next}`;

	function show() {
		tip = document.createElement('div');
		tip.id = id;
		tip.className = 'tooltip';
		tip.setAttribute('role', 'tooltip');
		tip.textContent = options.text;
		const rect = node.getBoundingClientRect();
		tip.style.left = `${rect.right + 8}px`;
		tip.style.top = `${rect.top + rect.height / 2}px`;
		document.body.append(tip);
		node.setAttribute('aria-describedby', id);
	}

	function schedule() {
		if (options.enabled === false || tip || timer) return;
		timer = setTimeout(() => {
			timer = undefined;
			show();
		}, TOOLTIP_DELAY_MS);
	}

	function hide() {
		clearTimeout(timer);
		timer = undefined;
		tip?.remove();
		tip = null;
		node.removeAttribute('aria-describedby');
	}

	function onKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') hide();
	}

	function onFocus() {
		if (node.matches(':focus-visible')) schedule();
	}

	node.addEventListener('pointerenter', schedule);
	node.addEventListener('pointerleave', hide);
	node.addEventListener('focus', onFocus);
	node.addEventListener('blur', hide);
	node.addEventListener('click', hide);
	node.addEventListener('keydown', onKeydown);

	return {
		update(updated) {
			options = updated;
			if (options.enabled === false) hide();
			else if (tip) tip.textContent = options.text;
		},
		destroy() {
			hide();
			node.removeEventListener('pointerenter', schedule);
			node.removeEventListener('pointerleave', hide);
			node.removeEventListener('focus', onFocus);
			node.removeEventListener('blur', hide);
			node.removeEventListener('click', hide);
			node.removeEventListener('keydown', onKeydown);
		}
	};
};
