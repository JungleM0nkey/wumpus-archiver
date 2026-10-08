<!--
	Browse's jump rail: a channel's years and months, each month with its message count
	from the channel's activity, the month in view marked. Picking a month calls
	`onjump`, which opens the reader at that month's first message. Below it, the
	channel's facts and the reader's keys.
-->
<script lang="ts">
	import type { ChannelActivityBucket } from '#lib/types.ts';
	import Kbd from './ui/Kbd.svelte';
	import Skeleton from './ui/Skeleton.svelte';

	let {
		buckets,
		current = null,
		onjump
	}: {
		/** The channel's months, oldest first; null while they load. */
		buckets: ChannelActivityBucket[] | null;
		/** The month in view, YYYY-MM. */
		current?: string | null;
		onjump: (bucket: ChannelActivityBucket) => void;
	} = $props();

	interface Month {
		key: string;
		short: string;
		label: string;
		bucket: ChannelActivityBucket;
	}

	const monthName = (bucket: ChannelActivityBucket, month: 'short' | 'long') =>
		new Date(`${bucket.start}T00:00:00Z`).toLocaleDateString('en-US', { month, timeZone: 'UTC' });

	const years = $derived.by(() => {
		const byYear: { year: string; total: number; months: Month[] }[] = [];
		for (const bucket of buckets ?? []) {
			const year = bucket.start.slice(0, 4);
			let group = byYear[byYear.length - 1];
			if (!group || group.year !== year) {
				group = { year, total: 0, months: [] };
				byYear.push(group);
			}
			group.total += bucket.messages;
			const count = `${bucket.messages.toLocaleString()} ${bucket.messages === 1 ? 'message' : 'messages'}`;
			group.months.push({
				key: bucket.start.slice(0, 7),
				short: monthName(bucket, 'short'),
				label: `${monthName(bucket, 'long')} ${year}, ${count}`,
				bucket
			});
		}
		return byYear;
	});

	const busiest = $derived(Math.max(1, ...(buckets ?? []).map((b) => b.messages)));
	const total = $derived((buckets ?? []).reduce((n, b) => n + b.messages, 0));
	const span = $derived.by(() => {
		if (!buckets?.length) return '';
		const name = (b: ChannelActivityBucket) => `${monthName(b, 'short')} ${b.start.slice(0, 4)}`;
		const first = name(buckets[0]);
		const last = name(buckets[buckets.length - 1]);
		return first === last ? first : `${first} – ${last}`;
	});
</script>

<nav class="rail" aria-label="Jump to a month">
	<h2 class="rail-title">Jump to</h2>

	{#if buckets === null}
		<div class="rail-skeleton" aria-busy="true">
			<span class="sr-only" role="status">Loading months…</span>
			{#each [0, 1, 2, 3] as i (i)}
				<Skeleton height="14px" width={`${80 - i * 10}%`} />
			{/each}
		</div>
	{:else}
		{#each years as group (group.year)}
			<section class="year">
				<h3 class="year-title">
					<span>{group.year}</span>
					<span class="mono">{group.total.toLocaleString()}</span>
				</h3>
				<ul>
					{#each group.months as month (month.key)}
						<li>
							<button
								type="button"
								class="month"
								aria-label={month.label}
								aria-current={month.key === current ? 'location' : undefined}
								onclick={() => onjump(month.bucket)}
							>
								<span class="month-name">{month.short}</span>
								<span class="bar" aria-hidden="true">
									<span style:width="{(month.bucket.messages / busiest) * 100}%"></span>
								</span>
								<span class="month-count mono">{month.bucket.messages.toLocaleString()}</span>
							</button>
						</li>
					{/each}
				</ul>
			</section>
		{/each}

		{#if span}
			<p class="facts">
				<span class="mono">{total.toLocaleString()}</span>
				{total === 1 ? 'message' : 'messages'}, {span}
			</p>
		{/if}
	{/if}

	<dl class="keys">
		<div>
			<dt><Kbd>J</Kbd> <Kbd>K</Kbd></dt>
			<dd>Next, previous message</dd>
		</div>
		<div>
			<dt><Kbd>G</Kbd> <Kbd>L</Kbd></dt>
			<dd>Newest messages</dd>
		</div>
	</dl>
</nav>

<style>
	.rail {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-4);
	}

	.rail-title {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-secondary);
	}

	.rail-skeleton {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.year-title {
		display: flex;
		justify-content: space-between;
		padding: 0 var(--space-2) var(--space-1);
		font: var(--type-label-md);
		color: var(--text-primary);
	}

	.year-title .mono {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	ul {
		list-style: none;
	}

	.month {
		display: grid;
		grid-template-columns: 32px 1fr auto;
		align-items: center;
		gap: var(--space-2);
		width: 100%;
		height: 28px;
		padding: 0 var(--space-2);
		border-radius: var(--radius-sm);
		font: var(--type-label-sm);
		color: var(--text-secondary);
		text-align: left;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.month:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.month[aria-current='location'] {
		background: var(--bg-active);
		color: var(--text-primary);
	}

	.bar {
		height: 4px;
		border-radius: var(--radius-full);
		background: var(--bg-inset);
		overflow: hidden;
	}

	.bar span {
		display: block;
		height: 100%;
		min-width: 2px;
		border-radius: inherit;
		background: var(--text-tertiary);
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.month:hover .bar span,
	.month[aria-current='location'] .bar span {
		background: var(--accent);
	}

	.month-count {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.facts {
		padding: var(--space-3) var(--space-2) 0;
		border-top: 1px solid var(--border-subtle);
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.keys {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: 0 var(--space-2);
	}

	.keys div {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.keys dt {
		display: inline-flex;
		gap: 2px;
		flex-shrink: 0;
	}

	.keys dd {
		font: var(--type-label-xs);
		color: var(--text-tertiary);
	}
</style>
