<!--
	The Archive screen's attachments-on-disk card: how many image attachments are local
	attachments in the attachments dir, what they take on disk, and the same per
	channel, from /api/downloads/stats. It covers the whole archive, every guild.
-->
<script lang="ts">
	import type { DownloadStatsResponse } from '#lib/types.ts';
	import Alert from '../ui/Alert.svelte';
	import Badge from '../ui/Badge.svelte';
	import Button from '../ui/Button.svelte';
	import EmptyState from '../ui/EmptyState.svelte';
	import Icon from '../ui/Icon.svelte';
	import ProgressBar from '../ui/ProgressBar.svelte';
	import { formatBytes, percent } from './format.ts';

	let { stats, error = '' }: { stats: DownloadStatsResponse | null; error?: string } = $props();

	/** Channels shown before "Show all". */
	const SHOWN = 8;

	let showAll = $state(false);

	const complete = $derived(stats ? percent(stats.downloaded, stats.total_images) : 0);
	const channels = $derived(stats ? (showAll ? stats.channels : stats.channels.slice(0, SHOWN)) : []);
</script>

<section class="card" aria-labelledby="attachments-title">
	<header class="card-header">
		<h2 class="card-title" id="attachments-title">
			<Icon name="download" />
			Attachments on disk
		</h2>
		{#if stats?.attachments_dir}
			<Badge icon="folder" mono title="Attachments dir: {stats.attachments_dir}">{stats.attachments_dir}</Badge>
		{:else if stats}
			<Badge tone="warning" icon="folder">No attachments dir</Badge>
		{/if}
	</header>

	<div class="card-body">
		{#if error}
			<Alert tone="danger" title="Download stats could not be read">{error}</Alert>
		{:else if !stats}
			<p class="note">Download stats are not available.</p>
		{:else if stats.total_images === 0}
			<EmptyState
				icon="images"
				title="No image attachments in the archive yet."
				description="A scrape records attachments; downloading them makes them local attachments."
				compact
			/>
		{:else}
			<dl class="summary">
				<div class="stat">
					<dt>Local attachments</dt>
					<dd class="mono">{stats.downloaded.toLocaleString()}</dd>
				</div>
				<div class="stat">
					<dt>Image attachments</dt>
					<dd class="mono">{stats.total_images.toLocaleString()}</dd>
				</div>
				<div class="stat">
					<dt>On disk</dt>
					<dd class="mono">{formatBytes(stats.downloaded_bytes)}</dd>
				</div>
				<div class="stat">
					<dt>Downloaded</dt>
					<dd class="mono">{complete}%</dd>
				</div>
			</dl>

			<div class="overall">
				<ProgressBar label="Image attachments downloaded" value={complete} tone={complete === 100 ? 'success' : 'accent'} />
				<div class="breakdown">
					{#if stats.pending > 0}
						<Badge tone="warning" mono>{stats.pending.toLocaleString()} pending</Badge>
					{/if}
					{#if stats.failed > 0}
						<Badge tone="danger" mono>{stats.failed.toLocaleString()} failed</Badge>
					{/if}
					{#if stats.skipped > 0}
						<Badge mono>{stats.skipped.toLocaleString()} skipped</Badge>
					{/if}
				</div>
			</div>

			{#if stats.channels.length > 0}
				<div class="table-wrap">
					<table class="table">
						<caption class="sr-only">Image attachments per channel</caption>
						<thead>
							<tr>
								<th scope="col">Channel</th>
								<th scope="col" class="num">Local</th>
								<th scope="col" class="num md">Pending</th>
								<th scope="col" class="num md">Failed</th>
								<th scope="col" class="num sm">Total</th>
								<th scope="col" class="num md">Size</th>
								<th scope="col" class="bar-col">Downloaded</th>
							</tr>
						</thead>
						<tbody>
							{#each channels as ch (ch.channel_id)}
								{@const pct = percent(ch.downloaded, ch.total_images)}
								<tr>
									<td class="name"><span class="truncate">#{ch.channel_name}</span></td>
									<td class="num mono">{ch.downloaded.toLocaleString()}</td>
									<td class="num mono md" class:dim={ch.pending === 0}>{ch.pending.toLocaleString()}</td>
									<td class="num mono md" class:dim={ch.failed === 0} class:bad={ch.failed > 0}>
										{ch.failed.toLocaleString()}
									</td>
									<td class="num mono sm">{ch.total_images.toLocaleString()}</td>
									<td class="num mono md">{formatBytes(ch.downloaded_bytes)}</td>
									<td class="bar-col">
										<span class="cell-bar">
											<ProgressBar label="#{ch.channel_name} downloaded" value={pct} size="sm" tone={pct === 100 ? 'success' : 'accent'} />
											<span class="mono pct">{pct}%</span>
										</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if stats.channels.length > SHOWN}
					<Button variant="ghost" size="sm" onclick={() => (showAll = !showAll)} aria-expanded={showAll}>
						{showAll ? 'Show fewer' : `Show all ${stats.channels.length} channels`}
					</Button>
				{/if}
			{/if}
		{/if}
	</div>
</section>

<style>
	.card {
		container-type: inline-size;
		min-width: 0;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
	}

	.card-header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2) var(--space-3);
		min-height: 52px;
		padding: var(--space-3) var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
		min-width: 0;
	}

	.card-header :global(.badge) {
		max-width: min(420px, 55%);
	}

	.card-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-heading-sm);
		white-space: nowrap;
	}

	.card-title :global(.icon) {
		color: var(--text-secondary);
	}

	.card-body {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: var(--space-4);
		padding: var(--space-5);
	}

	.card-body > :global(.button) {
		align-self: flex-start;
	}

	.note {
		font: var(--type-body-sm);
		color: var(--text-tertiary);
	}

	.summary {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--space-3);
		padding: var(--space-4);
		background: var(--bg-raised);
		border-radius: var(--radius-sm);
	}

	.stat {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}

	.stat dt {
		order: 2;
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.stat dd {
		font: var(--type-mono-num-lg);
		font-size: 22px;
		line-height: 28px;
	}

	.overall {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.breakdown {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.breakdown:empty {
		display: none;
	}

	.table-wrap {
		overflow-x: auto;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
	}

	.table {
		width: 100%;
		border-collapse: collapse;
		font: var(--type-body-sm);
	}

	.table th {
		padding: var(--space-2) var(--space-3);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		text-align: left;
		color: var(--text-tertiary);
		background: var(--bg-raised);
		border-bottom: 1px solid var(--border-subtle);
		white-space: nowrap;
	}

	.table td {
		height: 36px;
		padding: 0 var(--space-3);
		border-bottom: 1px solid var(--border-subtle);
		white-space: nowrap;
	}

	.table tbody tr:last-child td {
		border-bottom: none;
	}

	.table tbody tr {
		transition: background-color var(--duration-micro) var(--ease-out-quint);
	}

	.table tbody tr:hover {
		background: var(--bg-hover);
	}

	.table .num {
		text-align: right;
	}

	.table td.mono {
		font-size: 12px;
	}

	.name .truncate {
		display: block;
		max-width: 240px;
	}

	.dim {
		color: var(--text-tertiary);
	}

	.bad {
		color: var(--danger);
	}

	.bar-col {
		width: 160px;
	}

	.cell-bar {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.pct {
		min-width: 36px;
		font-size: 11px;
		text-align: right;
		color: var(--text-tertiary);
	}

	/* Narrower cards keep each channel's local and total counts and its bar. */
	@container (max-width: 640px) {
		.summary {
			grid-template-columns: repeat(2, 1fr);
		}

		.card-header :global(.badge) {
			max-width: 100%;
		}

		.md {
			display: none;
		}

		.bar-col {
			width: 120px;
		}

		.name .truncate {
			max-width: 120px;
		}
	}

	@container (max-width: 420px) {
		.sm {
			display: none;
		}

		.table td,
		.table th {
			padding-inline: var(--space-2);
		}
	}
</style>
