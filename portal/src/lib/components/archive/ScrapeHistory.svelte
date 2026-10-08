<!--
	The Archive screen's scrape job history: every scrape job that ended since the
	server started, the most recent first.
-->
<script lang="ts">
	import { shell } from '#lib/shell.svelte.ts';
	import type { ScrapeJob } from '#lib/types.ts';
	import Alert from '../ui/Alert.svelte';
	import Badge from '../ui/Badge.svelte';
	import EmptyState from '../ui/EmptyState.svelte';
	import Icon from '../ui/Icon.svelte';
	import { formatDateTime, formatDuration, jobGuildName, jobStatus } from './format.ts';

	let { jobs, error = '' }: { jobs: ScrapeJob[]; error?: string } = $props();
</script>

<section class="card" aria-labelledby="history-title">
	<header class="card-header">
		<h2 class="card-title" id="history-title">
			<Icon name="history" />
			Scrape job history
		</h2>
		{#if jobs.length > 0}
			<span class="count mono">{jobs.length} job{jobs.length === 1 ? '' : 's'}</span>
		{/if}
	</header>

	{#if error}
		<div class="pad"><Alert tone="danger" title="Scrape job history could not be read">{error}</Alert></div>
	{:else if jobs.length === 0}
		<EmptyState
			icon="history"
			title="No scrape jobs have ended yet."
			description="The history lists the jobs that ended since the server started."
			compact
		/>
	{:else}
		<div class="table-wrap">
			<table class="table">
				<caption class="sr-only">Scrape jobs that ended, most recent first</caption>
				<thead>
					<tr>
						<th scope="col">Status</th>
						<th scope="col">Guild</th>
						<th scope="col" class="num md">Channels</th>
						<th scope="col" class="num">Messages</th>
						<th scope="col" class="num md">Attachments</th>
						<th scope="col" class="num sm">Duration</th>
						<th scope="col" class="md">Started</th>
						<th scope="col" class="lg">Job</th>
					</tr>
				</thead>
				<tbody>
					{#each jobs as job (job.id)}
						{@const status = jobStatus(job.status)}
						<tr>
							<td><Badge tone={status.tone} icon={status.icon}>{status.label}</Badge></td>
							<td class="guild"><span class="truncate" title={job.error_message ?? undefined}>{jobGuildName(job, shell.guilds)}</span></td>
							<td class="num mono md">{job.progress.channels_done.toLocaleString()}</td>
							<td class="num mono">{job.progress.messages_scraped.toLocaleString()}</td>
							<td class="num mono md">{job.progress.attachments_found.toLocaleString()}</td>
							<td class="num mono sm">{formatDuration(job.duration_seconds)}</td>
							<td class="mono md">{formatDateTime(job.started_at)}</td>
							<td class="mono lg dim">{job.id}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>

<style>
	.card {
		container-type: inline-size;
		min-width: 0;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	.card-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		min-height: 52px;
		padding: var(--space-3) var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
	}

	.card-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-heading-sm);
	}

	.card-title :global(.icon) {
		color: var(--text-secondary);
	}

	.count {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.pad {
		padding: var(--space-5);
	}

	.table-wrap {
		overflow-x: auto;
	}

	.table {
		width: 100%;
		border-collapse: collapse;
		font: var(--type-body-sm);
	}

	.table th {
		padding: var(--space-2) var(--space-4);
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
		height: 40px;
		padding: 0 var(--space-4);
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

	.guild .truncate {
		display: block;
		max-width: 220px;
	}

	.dim {
		color: var(--text-tertiary);
	}

	/* Narrower cards keep the columns that say what each job was: its status, guild, messages. */
	@container (max-width: 900px) {
		.lg {
			display: none;
		}
	}

	@container (max-width: 640px) {
		.md {
			display: none;
		}

		.table th,
		.table td {
			padding-inline: var(--space-3);
		}

		.guild .truncate {
			max-width: 120px;
		}
	}

	@container (max-width: 420px) {
		.sm {
			display: none;
		}

		.table th,
		.table td {
			padding-inline: var(--space-2);
		}

		.guild .truncate {
			max-width: 88px;
		}
	}
</style>
