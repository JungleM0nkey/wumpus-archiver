<!--
	The Search screen's query bar: the chips in force as removable pills, then the field
	for terms and new chips, with Clear and Search. Typing `in:`, `from:` or `has:` opens
	suggestions (channels, matching authors, the kinds); picking one adds its chip and
	searches. Backspace in an empty field removes the last chip.
-->
<script module lang="ts">
	import type { IconName } from '../ui/icons.ts';
	import type { Chip, ChipKind } from '#lib/search.ts';

	/** One suggestion for the chip being typed. */
	export interface Suggestion {
		chip: Chip;
		label: string;
		detail?: string;
		avatar?: string | null;
	}

	const CHIP_ICONS: Record<ChipKind, IconName> = {
		in: 'hash',
		from: 'user',
		has: 'paperclip',
		after: 'calendar',
		before: 'calendar'
	};

	const HAS_ICONS: Record<string, IconName> = {
		file: 'file',
		image: 'image',
		video: 'video',
		link: 'link'
	};

	/** The icon of a chip: its kind's, or for `has:` the kind of thing it asks for. */
	export function chipIcon(chip: Chip): IconName {
		if (chip.kind === 'has') return HAS_ICONS[chip.value] ?? 'paperclip';
		return CHIP_ICONS[chip.kind];
	}
</script>

<script lang="ts">
	import Avatar from '../ui/Avatar.svelte';
	import Button from '../ui/Button.svelte';
	import Icon from '../ui/Icon.svelte';
	import IconButton from '../ui/IconButton.svelte';
	import { HAS_KINDS, chipText, typingChip } from '#lib/search.ts';

	let {
		chips,
		draft = $bindable(''),
		channels,
		findAuthors,
		onsubmit,
		onremove,
		onclear,
		input = $bindable()
	}: {
		chips: Chip[];
		/** The field's text: terms, and chips not yet searched for. */
		draft?: string;
		/** The channel names `in:` suggests. */
		channels: string[];
		/** The authors `from:` suggests for what has been typed after it. */
		findAuthors: (partial: string) => Promise<Suggestion[]>;
		/** Search for the field's text, with `chip` added when one was picked. */
		onsubmit: (draft: string, chip?: Chip) => void;
		onremove: (chip: Chip) => void;
		onclear: () => void;
		input?: HTMLInputElement;
	} = $props();

	const LISTBOX_ID = 'search-suggestions';

	let suggestions: Suggestion[] = $state([]);
	let active = $state(-1);
	let typed = $state<ReturnType<typeof typingChip>>(null);
	let lookups = 0;

	const open = $derived(typed !== null && suggestions.length > 0);

	async function suggest() {
		// The field's own value: this may run before the binding updates `draft`.
		const value = input?.value ?? draft;
		typed = input && input.selectionEnd === value.length ? typingChip(value) : null;
		active = -1;
		const now = typed;
		if (!now) {
			suggestions = [];
			return;
		}
		const partial = now.partial.toLowerCase();
		if (now.kind === 'in') {
			suggestions = channels
				.filter((name) => name.toLowerCase().includes(partial))
				.slice(0, 8)
				.map((name) => ({ chip: { kind: 'in', value: name }, label: `#${name}` }));
		} else if (now.kind === 'has') {
			suggestions = HAS_KINDS.filter((kind) => kind.startsWith(partial)).map((kind) => ({
				chip: { kind: 'has', value: kind },
				label: kind
			}));
		} else if (now.kind === 'from') {
			const lookup = ++lookups;
			const found = await findAuthors(now.partial);
			if (lookup === lookups && typed === now) suggestions = found;
		} else {
			suggestions = [];
		}
	}

	function close() {
		typed = null;
		suggestions = [];
		active = -1;
	}

	function pick(suggestion: Suggestion) {
		const at = typed?.at ?? draft.length;
		const rest = draft.slice(0, at).trim();
		close();
		draft = rest;
		onsubmit(rest, suggestion.chip);
	}

	function onkeydown(event: KeyboardEvent) {
		if (open && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
			event.preventDefault();
			const step = event.key === 'ArrowDown' ? 1 : -1;
			active = (active + step + suggestions.length) % suggestions.length;
		} else if (event.key === 'Enter') {
			event.preventDefault();
			if (open && active >= 0) pick(suggestions[active]);
			else {
				close();
				onsubmit(draft);
			}
		} else if (event.key === 'Tab' && open && active >= 0) {
			event.preventDefault();
			pick(suggestions[active]);
		} else if (event.key === 'Escape') {
			if (open) {
				event.preventDefault();
				close();
			}
		} else if (event.key === 'Backspace' && !draft && input?.selectionStart === 0 && chips.length) {
			event.preventDefault();
			onremove(chips[chips.length - 1]);
		}
	}
</script>

<form
	class="query-bar"
	role="search"
	onsubmit={(event) => {
		event.preventDefault();
		close();
		onsubmit(draft);
	}}
>
	<div class="field">
		<Icon name="search" size={18} />
		<ul class="chips" aria-label="Filters">
			{#each chips as chip (chip.kind)}
				<li class="chip">
					<Icon name={chipIcon(chip)} size={14} />
					<span class="chip-kind">{chip.kind}:</span><span class="chip-value">{chip.value}</span>
					<button
						type="button"
						class="chip-remove"
						aria-label={`Remove ${chipText(chip)}`}
						title={`Remove ${chipText(chip)}`}
						onclick={() => onremove(chip)}
					>
						<Icon name="x" size={14} />
					</button>
				</li>
			{/each}
		</ul>
		<input
			bind:this={input}
			bind:value={draft}
			type="text"
			role="combobox"
			class="query-input"
			data-view-search
			placeholder={chips.length ? 'Add words or filters' : 'Search messages, or filter with in: from: has: after: before:'}
			aria-label="Search query"
			aria-autocomplete="list"
			aria-expanded={open}
			aria-controls={LISTBOX_ID}
			aria-activedescendant={open && active >= 0 ? `${LISTBOX_ID}-${active}` : undefined}
			autocomplete="off"
			spellcheck="false"
			oninput={suggest}
			onclick={suggest}
			onblur={() => setTimeout(close, 120)}
			{onkeydown}
		/>
		{#if draft || chips.length}
			<IconButton icon="x" label="Clear search" size="sm" onclick={onclear} />
		{/if}
		<ul id={LISTBOX_ID} class="suggestions" role="listbox" aria-label="Suggestions" hidden={!open}>
			{#each suggestions as suggestion, i (chipText(suggestion.chip))}
				<li
					id={`${LISTBOX_ID}-${i}`}
					role="option"
					aria-selected={i === active}
					class="suggestion"
					class:active={i === active}
					onpointerdown={(event) => {
						event.preventDefault();
						pick(suggestion);
					}}
				>
					{#if suggestion.chip.kind === 'from'}
						<Avatar src={suggestion.avatar} name={suggestion.label} size={20} />
					{:else}
						<Icon name={chipIcon(suggestion.chip)} size={14} />
					{/if}
					<span class="suggestion-label">{suggestion.label}</span>
					{#if suggestion.detail}<span class="suggestion-detail">{suggestion.detail}</span>{/if}
				</li>
			{/each}
		</ul>
	</div>
	<Button type="submit" variant="primary">Search</Button>
</form>

<style>
	.query-bar {
		display: flex;
		align-items: flex-start;
		gap: var(--space-2);
	}

	.field {
		position: relative;
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-2);
		min-height: 44px;
		padding: var(--space-1) var(--space-2) var(--space-1) var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		color: var(--text-tertiary);
		transition:
			border-color var(--duration-micro) var(--ease-out-quint),
			box-shadow var(--duration-micro) var(--ease-out-quint);
	}

	.field:hover {
		border-color: var(--border-strong);
	}

	.field:focus-within {
		border-color: var(--accent-glow);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}

	.chips {
		display: contents;
		list-style: none;
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		height: 26px;
		padding: 0 2px 0 var(--space-2);
		border: 1px solid var(--accent-glow);
		border-radius: var(--radius-full);
		background: var(--accent-muted);
		color: var(--accent);
		font: var(--type-label-sm);
		white-space: nowrap;
		animation: scale-in var(--duration-small) var(--ease-out-quint);
	}

	.chip-kind {
		color: var(--text-secondary);
	}

	.chip-value {
		max-width: 180px;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.chip-remove {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 20px;
		height: 20px;
		border-radius: var(--radius-full);
		color: var(--text-secondary);
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.chip-remove:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.query-input {
		flex: 1;
		min-width: 160px;
		height: 34px;
		font: var(--type-body-md);
		color: var(--text-primary);
	}

	.query-input:focus-visible {
		outline: none;
	}

	.query-input::placeholder {
		color: var(--text-tertiary);
	}

	.suggestions {
		position: absolute;
		top: calc(100% + var(--space-1));
		left: 0;
		z-index: 20;
		min-width: 260px;
		max-width: 100%;
		padding: var(--space-1);
		list-style: none;
		background: var(--bg-overlay);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-floating);
		animation: scale-in var(--duration-medium) var(--ease-out-quint);
	}

	.suggestions[hidden] {
		display: none;
	}

	.suggestion {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		height: 32px;
		padding: 0 var(--space-2);
		border-radius: var(--radius-sm);
		color: var(--text-secondary);
		font: var(--type-label-md);
		cursor: pointer;
	}

	.suggestion:hover,
	.suggestion.active {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.suggestion-label {
		color: var(--text-primary);
	}

	.suggestion-detail {
		margin-left: auto;
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.query-bar :global(.button) {
		height: 44px;
	}

	@media (max-width: 600px) {
		.field {
			padding-left: var(--space-3);
		}

		.query-input {
			min-width: 120px;
		}
	}
</style>
