// The Search screen's query: free text plus filter chips, written in the text itself.
//
// `in:general from:alice has:link after:2024-05-01 before:2024-06-01 deploy` is five
// chips and one search term. The whole text is the URL's `q`, so a chip typed, picked
// from a facet or removed is a new URL, and reload and back/forward restore it. Each
// kind holds one value (the API filters by one channel and one author); a later chip
// of a kind replaces an earlier one. A token that looks like a chip but has no valid
// value (`has:gif`, `after:May`) stays in the text, as a term.

/** The kinds of chip, in the order the query text writes them. */
export const CHIP_KINDS = ['in', 'from', 'has', 'after', 'before'] as const;
export type ChipKind = (typeof CHIP_KINDS)[number];

/** What `has:` takes: the API's `has` values. */
export const HAS_KINDS = ['file', 'image', 'video', 'link'] as const;
export type HasKind = (typeof HAS_KINDS)[number];

export interface Chip {
	kind: ChipKind;
	/** A channel name, a username, a `HasKind` or a `YYYY-MM-DD` day. */
	value: string;
}

export interface SearchQuery {
	/** The search terms: what is left of the text once the chips are taken out. */
	text: string;
	/** At most one chip of each kind, in CHIP_KINDS order. */
	chips: Chip[];
}

const TOKEN = /"[^"]*"?|\S+/g;
const CHIP = /^(in|from|has|after|before):(.+)$/i;
const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Whether `value` is a real calendar day written `YYYY-MM-DD`. */
export function isDay(value: string): boolean {
	const match = DAY.exec(value);
	if (!match) return false;
	const [, y, m, d] = match.map(Number);
	const date = new Date(Date.UTC(y, m - 1, d));
	return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}

/** The chip a token is, or null when it is a term. */
export function chipOf(token: string): Chip | null {
	const match = CHIP.exec(token);
	if (!match) return null;
	const kind = match[1].toLowerCase() as ChipKind;
	let value = match[2];
	if (kind === 'in') value = value.replace(/^#/, '');
	if (kind === 'from') value = value.replace(/^@/, '');
	if (kind === 'has') value = value.toLowerCase();
	if (!value) return null;
	if (kind === 'has' && !(HAS_KINDS as readonly string[]).includes(value)) return null;
	if ((kind === 'after' || kind === 'before') && !isDay(value)) return null;
	return { kind, value };
}

/** Sort chips into CHIP_KINDS order, keeping the last of each kind. */
function canonical(chips: Chip[]): Chip[] {
	const byKind = new Map<ChipKind, Chip>();
	for (const chip of chips) byKind.set(chip.kind, chip);
	return CHIP_KINDS.flatMap((kind) => byKind.get(kind) ?? []);
}

/** Read the chips and terms out of query text. */
export function parseQuery(input: string): SearchQuery {
	const chips: Chip[] = [];
	const terms: string[] = [];
	for (const token of input.match(TOKEN) ?? []) {
		const chip = token.startsWith('"') ? null : chipOf(token);
		if (chip) chips.push(chip);
		else terms.push(token);
	}
	return { text: terms.join(' '), chips: canonical(chips) };
}

/** The query text for `query`: its chips, then its terms. */
export function formatQuery(query: SearchQuery): string {
	return [...canonical(query.chips).map(chipText), query.text.trim()].filter(Boolean).join(' ');
}

/** A chip as the query text writes it, such as `from:alice`. */
export function chipText(chip: Chip): string {
	return `${chip.kind}:${chip.value}`;
}

/** `query` with `chip` in place of any chip of its kind. */
export function withChip(query: SearchQuery, ...chips: Chip[]): SearchQuery {
	return { text: query.text, chips: canonical([...query.chips, ...chips]) };
}

/** `query` without its chips of `kinds`. */
export function withoutChips(query: SearchQuery, ...kinds: ChipKind[]): SearchQuery {
	return { text: query.text, chips: query.chips.filter((c) => !kinds.includes(c.kind)) };
}

/** The kinds of chip that name something in one guild: a channel, an author. */
export const GUILD_BOUND_CHIPS: ChipKind[] = ['in', 'from'];

/** Query text `input` without its chips of `kinds`; the rest stays as written. */
export function dropChips(input: string, ...kinds: ChipKind[]): string {
	return (input.match(TOKEN) ?? [])
		.filter((token) => {
			const chip = token.startsWith('"') ? null : chipOf(token);
			return !chip || !kinds.includes(chip.kind);
		})
		.join(' ');
}

/** The value of `query`'s chip of `kind`, or undefined. */
export function chipValue(query: SearchQuery, kind: ChipKind): string | undefined {
	return query.chips.find((c) => c.kind === kind)?.value;
}

/** Whether `query` asks for anything: terms, or a chip that filters (any chip does). */
export function isEmpty(query: SearchQuery): boolean {
	return !query.text.trim() && query.chips.length === 0;
}

/** The `after:` and `before:` chips that bound the calendar month starting on `start`. */
export function monthChips(start: string): Chip[] {
	const [y, m] = start.split('-').map(Number);
	const next = new Date(Date.UTC(y, m, 1));
	const day = (d: Date) => d.toISOString().slice(0, 10);
	return [
		{ kind: 'after', value: day(new Date(Date.UTC(y, m - 1, 1))) },
		{ kind: 'before', value: day(next) }
	];
}

/**
 * The chip being typed at the end of `draft`, when its last token is a chip kind and a
 * colon: its kind and what follows the colon so far. It drives the suggestions.
 */
export function typingChip(draft: string): { kind: ChipKind; partial: string; at: number } | null {
	const match = /(?:^|\s)(in|from|has|after|before):(\S*)$/i.exec(draft);
	if (!match) return null;
	const at = match.index + (match[0].length - match[1].length - match[2].length - 1);
	return { kind: match[1].toLowerCase() as ChipKind, partial: match[2].replace(/^[#@]/, ''), at };
}

// ── The highlight ───────────────────────────────────────────────────────────

/** A run of a snippet's text, marked when it is a match. */
export interface SnippetRun {
	text: string;
	mark: boolean;
}

const ENTITIES: Record<string, string> = {
	'&amp;': '&',
	'&lt;': '<',
	'&gt;': '>',
	'&quot;': '"',
	'&#x27;': "'",
	'&#39;': "'"
};

/**
 * The runs of a result's `highlight`, as text to render, never as HTML. The API
 * escapes the content and marks matches with `<mark>`; this splits on the marks and
 * unescapes the rest, so the page sets text nodes and no markup reaches the DOM.
 */
export function snippetRuns(highlight: string): SnippetRun[] {
	const runs: SnippetRun[] = [];
	highlight.split(/(<mark>.*?<\/mark>)/s).forEach((part) => {
		if (!part) return;
		const mark = part.startsWith('<mark>') && part.endsWith('</mark>');
		const body = mark ? part.slice('<mark>'.length, -'</mark>'.length) : part;
		runs.push({ text: body.replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, (e) => ENTITIES[e]), mark });
	});
	return runs;
}
