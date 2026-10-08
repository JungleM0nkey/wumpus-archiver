<!--
	Messages per month as an area chart: an SVG drawn at the container's width, with a
	y axis of message counts and an x axis of months. Every calendar month from the
	first active one to the last is a point (`.chart-point`, `data-month="YYYY-MM"`),
	months without messages at zero. Hovering, or arrow keys once focused, moves a
	crosshair and tooltip between months; a sentence sums it up and a table lists
	every month, so nothing depends on seeing the chart.
-->
<script lang="ts">
	import type { ActivityBucket } from '#lib/types.ts';

	let { buckets, label = 'Messages per month' }: { buckets: ActivityBucket[]; label?: string } =
		$props();

	interface Month {
		key: string;
		year: number;
		/** 0-based, as Date counts them. */
		month: number;
		messages: number;
	}

	const HEIGHT = 220;
	const MARGIN = { top: 24, right: 16, bottom: 28, left: 48 };

	const months = $derived.by((): Month[] => {
		if (buckets.length === 0) return [];
		const counts = new Map(buckets.map((b) => [b.start.slice(0, 7), b.messages]));
		const [y0, m0] = buckets[0].start.split('-').map(Number);
		const [y1, m1] = buckets[buckets.length - 1].start.split('-').map(Number);
		const all: Month[] = [];
		let year = y0;
		let month = m0 - 1;
		while (year < y1 || (year === y1 && month <= m1 - 1)) {
			const key = `${year}-${String(month + 1).padStart(2, '0')}`;
			all.push({ key, year, month, messages: counts.get(key) ?? 0 });
			month += 1;
			if (month === 12) {
				month = 0;
				year += 1;
			}
		}
		return all;
	});

	function monthName(m: Month, withYear = true): string {
		return new Date(Date.UTC(m.year, m.month, 1)).toLocaleDateString('en-US', {
			month: 'short',
			year: withYear ? 'numeric' : undefined,
			timeZone: 'UTC'
		});
	}

	function plural(n: number, one: string, many: string): string {
		return `${n.toLocaleString()} ${n === 1 ? one : many}`;
	}

	const total = $derived(months.reduce((sum, m) => sum + m.messages, 0));
	const busiest = $derived(
		months.reduce<Month | null>((best, m) => (best === null || m.messages > best.messages ? m : best), null)
	);
	const summary = $derived.by(() => {
		if (months.length === 0 || !busiest) return 'No messages yet.';
		const first = months[0];
		const last = months[months.length - 1];
		if (months.length === 1) {
			return `All ${plural(total, 'message', 'messages')} are from ${monthName(first)}.`;
		}
		return (
			`${plural(total, 'message', 'messages')} over ${months.length} months, ` +
			`${monthName(first)} to ${monthName(last)}. ` +
			`Busiest: ${monthName(busiest)}, with ${plural(busiest.messages, 'message', 'messages')}.`
		);
	});

	let width = $state(640);
	const innerWidth = $derived(Math.max(width - MARGIN.left - MARGIN.right, 1));
	const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
	const baseline = MARGIN.top + innerHeight;

	/** Round tick steps (1, 2 or 5 times a power of ten) for at most about four ticks. */
	const ticks = $derived.by((): number[] => {
		const max = busiest?.messages ?? 0;
		if (max === 0) return [0, 1];
		const raw = max / 3;
		const power = Math.pow(10, Math.floor(Math.log10(raw)));
		const step = Math.max(1, [1, 2, 5, 10].map((f) => f * power).find((s) => s >= raw) ?? power * 10);
		const top = Math.ceil(max / step) * step;
		const out: number[] = [];
		for (let v = 0; v <= top; v += step) out.push(v);
		return out;
	});
	const yMax = $derived(ticks[ticks.length - 1]);

	function x(i: number): number {
		if (months.length === 1) return MARGIN.left + innerWidth / 2;
		return MARGIN.left + (i * innerWidth) / (months.length - 1);
	}

	function y(v: number): number {
		return MARGIN.top + innerHeight - (v / yMax) * innerHeight;
	}

	const line = $derived(months.map((m, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(m.messages)}`).join(''));
	const area = $derived(
		months.length > 1 ? `${line}L${x(months.length - 1)},${baseline}L${x(0)},${baseline}Z` : ''
	);

	/** Which months get an x-axis label: as many as fit, evenly strided, the year where it changes. */
	const xLabels = $derived.by(() => {
		const fit = Math.max(2, Math.floor(innerWidth / 72));
		const stride = Math.max(1, Math.ceil(months.length / fit));
		let year = -1;
		const out: { i: number; text: string; anchor: 'start' | 'middle' | 'end' }[] = [];
		months.forEach((m, i) => {
			if (i % stride !== 0) return;
			const text = monthName(m, m.year !== year);
			year = m.year;
			const anchor =
				months.length === 1 ? 'middle' : i === 0 ? 'start' : i === months.length - 1 ? 'end' : 'middle';
			out.push({ i, text, anchor });
		});
		return out;
	});

	let active = $state<number | null>(null);
	const activeMonth = $derived(active === null ? null : (months[active] ?? null));

	function nearest(event: PointerEvent): void {
		const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect();
		if (months.length === 1) {
			active = 0;
			return;
		}
		const step = innerWidth / (months.length - 1);
		const i = Math.round((event.clientX - rect.left - MARGIN.left) / step);
		active = Math.min(Math.max(i, 0), months.length - 1);
	}

	function onKey(event: KeyboardEvent): void {
		const last = months.length - 1;
		const current = active ?? last;
		const next =
			event.key === 'ArrowLeft'
				? current - 1
				: event.key === 'ArrowRight'
					? current + 1
					: event.key === 'Home'
						? 0
						: event.key === 'End'
							? last
							: null;
		if (next === null) return;
		event.preventDefault();
		active = Math.min(Math.max(next, 0), last);
	}

	/** The month the slider reports: the active one, else the latest. */
	const focusedIndex = $derived(active ?? months.length - 1);

	function describe(m: Month | undefined): string {
		return m ? `${monthName(m)}: ${plural(m.messages, 'message', 'messages')}` : '';
	}

	const tooltipAlign = $derived(
		active === null || months.length === 1 ? 'middle' : active === 0 ? 'start' : active === months.length - 1 ? 'end' : 'middle'
	);
</script>

<figure class="activity-chart">
	<figcaption>
		<span class="chart-title">{label}</span>
		<span class="chart-summary">{summary}</span>
	</figcaption>

	{#if months.length > 0}
		<div
			class="plot"
			bind:clientWidth={width}
			role="slider"
			aria-label="{label}: arrow keys read each month"
			aria-orientation="horizontal"
			aria-valuemin={0}
			aria-valuemax={months.length - 1}
			aria-valuenow={focusedIndex}
			aria-valuetext={describe(months[focusedIndex])}
			tabindex="0"
			onkeydown={onKey}
			onfocus={() => (active ??= months.length - 1)}
			onblur={() => (active = null)}
		>
			<svg
				width={width}
				height={HEIGHT}
				viewBox="0 0 {width} {HEIGHT}"
				aria-hidden="true"
				onpointermove={nearest}
				onpointerleave={() => (active = null)}
			>
				<text class="axis-title" x={0} y={12}>Messages</text>
				{#each ticks as tick (tick)}
					<line class="grid" x1={MARGIN.left} x2={width - MARGIN.right} y1={y(tick)} y2={y(tick)} />
					<text class="tick y-tick" x={MARGIN.left - 8} y={y(tick)} dy="0.32em" text-anchor="end">
						{tick.toLocaleString()}
					</text>
				{/each}
				{#each xLabels as l (l.i)}
					<text class="tick x-tick" x={x(l.i)} y={HEIGHT - 8} text-anchor={l.anchor}>{l.text}</text>
				{/each}

				{#if area}<path class="area" d={area} />{/if}
				{#if months.length > 1}
					<path class="line" d={line} />
				{:else}
					<!-- One month has no line to draw: a column of the same wash, capped by the line. -->
					{@const top = y(months[0].messages)}
					<path class="area" d="M{x(0) - 12},{baseline}V{top}H{x(0) + 12}V{baseline}Z" />
					<path class="line" d="M{x(0) - 12},{top}H{x(0) + 12}" />
				{/if}

				{#if activeMonth && active !== null}
					<line class="crosshair" x1={x(active)} x2={x(active)} y1={MARGIN.top} y2={baseline} />
				{/if}
				{#each months as m, i (m.key)}
					<circle
						class="chart-point"
						class:active={active === i}
						data-month={m.key}
						data-messages={m.messages}
						cx={x(i)}
						cy={y(m.messages)}
						r="4"
					/>
				{/each}
			</svg>

			{#if activeMonth && active !== null}
				<div
					class="chart-tooltip {tooltipAlign}"
					style:left="{x(active)}px"
					style:top="{y(activeMonth.messages)}px"
				>
					<span class="tooltip-month">{monthName(activeMonth)}</span>
					<span class="tooltip-value mono">{plural(activeMonth.messages, 'message', 'messages')}</span>
				</div>
			{/if}
		</div>

		<details class="chart-table">
			<summary>Show as a table</summary>
			<table>
				<thead>
					<tr><th scope="col">Month</th><th scope="col">Messages</th></tr>
				</thead>
				<tbody>
					{#each months as m (m.key)}
						<tr>
							<th scope="row">{monthName(m)}</th>
							<td class="mono">{m.messages.toLocaleString()}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</details>
	{/if}
</figure>

<style>
	.activity-chart {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		margin: 0;
	}

	figcaption {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.chart-title {
		font: var(--type-heading-sm);
		color: var(--text-primary);
	}

	.chart-summary {
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.plot {
		position: relative;
		border-radius: var(--radius-sm);
	}

	svg {
		display: block;
		overflow: visible;
		touch-action: pan-y;
	}

	.axis-title,
	.tick {
		font: var(--type-mono-sm);
		fill: var(--text-tertiary);
		font-variant-numeric: tabular-nums;
	}

	.grid {
		stroke: var(--border-subtle);
		stroke-width: 1;
		shape-rendering: crispEdges;
	}

	.area {
		fill: var(--accent);
		fill-opacity: 0.1;
	}

	.line {
		fill: none;
		stroke: var(--accent);
		stroke-width: 2;
		stroke-linejoin: round;
		stroke-linecap: round;
	}

	.crosshair {
		stroke: var(--border-strong);
		stroke-width: 1;
		shape-rendering: crispEdges;
	}

	.chart-point {
		fill: var(--accent);
		stroke: var(--bg-surface);
		stroke-width: 2;
		opacity: 0;
	}

	.chart-point.active {
		opacity: 1;
	}

	.chart-tooltip {
		position: absolute;
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 6px 10px;
		border: 1px solid var(--border-default);
		border-radius: var(--radius-xs);
		background: var(--bg-overlay);
		box-shadow: var(--shadow-floating);
		pointer-events: none;
		white-space: nowrap;
		translate: -50% calc(-100% - 12px);
	}

	.chart-tooltip.start {
		translate: -12px calc(-100% - 12px);
	}

	.chart-tooltip.end {
		translate: calc(-100% + 12px) calc(-100% - 12px);
	}

	.tooltip-month {
		font: var(--type-label-sm);
		color: var(--text-secondary);
	}

	.tooltip-value {
		font: var(--type-mono-md);
		color: var(--text-primary);
	}

	.chart-table summary {
		width: fit-content;
		font: var(--type-label-sm);
		color: var(--text-secondary);
		cursor: pointer;
	}

	.chart-table summary:hover {
		color: var(--text-primary);
	}

	.chart-table table {
		margin-top: var(--space-3);
		border-collapse: collapse;
		font: var(--type-body-sm);
	}

	.chart-table th,
	.chart-table td {
		padding: var(--space-1) var(--space-6) var(--space-1) 0;
		text-align: left;
		border-bottom: 1px solid var(--border-subtle);
	}

	.chart-table thead th {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.chart-table tbody th {
		font-weight: 400;
		color: var(--text-secondary);
	}

	.chart-table td {
		color: var(--text-primary);
		text-align: right;
		padding-right: 0;
	}
</style>
