<!--
	The Archive screen's live scrape job card: the current (or last) scrape job's status,
	progress, current channel, counters and per-channel status, and cancelling it after
	a confirmation. It shows what it is given; the screen reads the status
	(scrape-status.svelte.ts), which is polled only while the job runs.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import { shell } from '#lib/shell.svelte.ts';
	import type { ScrapeChannelProgress, ScrapeJob } from '#lib/types.ts';
	import Alert from '../ui/Alert.svelte';
	import Badge from '../ui/Badge.svelte';
	import Button from '../ui/Button.svelte';
	import EmptyState from '../ui/EmptyState.svelte';
	import Icon from '../ui/Icon.svelte';
	import ProgressBar from '../ui/ProgressBar.svelte';
	import { formatDateTime, formatDuration, jobGuildName, jobStatus } from './format.ts';

	let {
		job,
		busy,
		canCancel,
		oncancel
	}: {
		/** The status's current job: running, or the last one to end since the server started. */
		job: ScrapeJob | null;
		busy: boolean;
		/** Whether this portal may cancel it (scrape control has an API token). */
		canCancel: boolean;
		/** Cancel the job; rejects with a message to show when it could not. */
		oncancel: () => Promise<void>;
	} = $props();

	/** Channels shown before "Show all". */
	const SHOWN = 6;

	let confirming = $state(false);
	let cancelling = $state(false);
	let cancelError = $state('');
	let showAll = $state(false);

	const status = $derived(job ? jobStatus(job.status) : null);
	// The newest first: the channel being scraped leads the list.
	const channels = $derived([...(job?.progress.channels ?? [])].reverse());
	const shownChannels = $derived(showAll ? channels : channels.slice(0, SHOWN));
	const where = $derived.by(() => {
		if (!job) return '';
		if (job.status === 'pending') return 'Waiting to start';
		if (job.status === 'connecting') return 'Connecting to Discord';
		return job.progress.current_channel ? `#${job.progress.current_channel}` : 'No channel yet';
	});

	// A job that ends while the confirmation is open needs no confirming.
	$effect(() => {
		if (!busy) confirming = false;
	});

	async function askToCancel() {
		cancelError = '';
		confirming = true;
		await tick();
		document.getElementById('cancel-job-confirm')?.focus();
	}

	async function confirmCancel() {
		cancelling = true;
		cancelError = '';
		try {
			await oncancel();
			confirming = false;
		} catch (e) {
			cancelError = e instanceof Error ? e.message : 'The scrape job could not be cancelled';
		} finally {
			cancelling = false;
		}
	}

	function channelState(channel: ScrapeChannelProgress): 'done' | 'scraping' | 'stopped' {
		if (channel.done) return 'done';
		return busy ? 'scraping' : 'stopped';
	}
</script>

<section class="card job-card" aria-labelledby="job-card-title" data-state={busy ? 'running' : job ? 'ended' : 'idle'}>
	<header class="card-header">
		<h2 class="card-title" id="job-card-title">
			<Icon name="activity" />
			Scrape job
		</h2>
		{#if job && status}
			<Badge tone={status.tone} icon={status.icon}>{status.label}</Badge>
		{:else}
			<Badge icon="circle">idle</Badge>
		{/if}
	</header>

	{#if !job}
		<EmptyState
			icon="circle-dashed"
			title="No scrape job running."
			description="A job you start shows its progress here, channel by channel."
			compact
		/>
	{:else}
		<div class="card-body">
			<div class="job-head">
				<div class="job-guild">
					<span class="guild-name truncate">{jobGuildName(job, shell.guilds)}</span>
					<span class="job-meta mono">
						{job.id} · started {formatDateTime(job.started_at)}
					</span>
				</div>
				<div class="where" class:live={busy}>
					{#if busy}<span class="live-dot" aria-hidden="true"></span>{/if}
					<span class="truncate">{where}</span>
				</div>
			</div>

			{#if busy}
				<ProgressBar label="Scraping" size="sm" />
			{:else}
				<ProgressBar
					label="Scrape job {status?.label}"
					value={100}
					size="sm"
					tone={job.status === 'completed' ? 'success' : job.status === 'failed' ? 'danger' : 'neutral'}
				/>
			{/if}

			<dl class="counters">
				<div class="counter">
					<dt>Channels</dt>
					<dd class="mono">{job.progress.channels_done.toLocaleString()}</dd>
				</div>
				<div class="counter">
					<dt>Messages</dt>
					<dd class="mono">{job.progress.messages_scraped.toLocaleString()}</dd>
				</div>
				<div class="counter">
					<dt>Attachments</dt>
					{#if busy && job.progress.attachments_found === 0}
						<dd class="mono muted" title="Counted when the job finishes">—</dd>
					{:else}
						<dd class="mono">{job.progress.attachments_found.toLocaleString()}</dd>
					{/if}
				</div>
				<div class="counter">
					<dt>{busy ? 'Elapsed' : 'Duration'}</dt>
					<dd class="mono">{formatDuration(job.duration_seconds)}</dd>
				</div>
			</dl>

			{#if job.error_message}
				<Alert tone="danger" title="The scrape job failed">{job.error_message}</Alert>
			{/if}

			{#if channels.length > 0}
				<div class="channels">
					<h3 class="sub-title">
						Channels
						<span class="mono count">{job.progress.channels_done} of {channels.length} done</span>
					</h3>
					<ul class="channel-list" aria-label="Channel status">
						{#each shownChannels as channel, i (channels.length - i)}
							{@const state = channelState(channel)}
							<li class="channel-row" data-state={state}>
								<span class="channel-icon">
									<Icon
										name={state === 'done' ? 'circle-check' : state === 'scraping' ? 'circle-dot' : 'ban'}
										size={14}
									/>
								</span>
								<span class="channel-name truncate">#{channel.name}</span>
								<span class="channel-count mono">{channel.messages.toLocaleString()}</span>
								<span class="channel-state">{state}</span>
							</li>
						{/each}
					</ul>
					{#if channels.length > SHOWN}
						<Button variant="ghost" size="sm" onclick={() => (showAll = !showAll)} aria-expanded={showAll}>
							{showAll ? 'Show fewer' : `Show all ${channels.length} channels`}
						</Button>
					{/if}
				</div>
			{/if}

			{#if job.progress.errors.length > 0}
				<details class="warnings">
					<summary>
						<Icon name="triangle-alert" size={14} />
						{job.progress.errors.length} channel{job.progress.errors.length === 1 ? '' : 's'} could not be scraped
					</summary>
					<ul>
						{#each job.progress.errors as err, i (i)}
							<li>{err}</li>
						{/each}
					</ul>
				</details>
			{/if}

			{#if busy}
				<div class="cancel">
					{#if confirming}
						<div class="confirm" role="group" aria-labelledby="cancel-question">
							<p id="cancel-question" class="confirm-text">
								Cancel this scrape job? What it has written so far stays in the archive.
							</p>
							<div class="confirm-actions">
								<Button variant="secondary" size="sm" onclick={() => (confirming = false)}>Keep running</Button>
								<Button
									id="cancel-job-confirm"
									variant="danger"
									size="sm"
									icon="ban"
									loading={cancelling}
									onclick={confirmCancel}
								>
									Cancel job
								</Button>
							</div>
						</div>
					{:else}
						<Button variant="danger" size="sm" icon="ban" disabled={!canCancel} onclick={askToCancel}>
							Cancel scrape job
						</Button>
						{#if !canCancel}
							<span class="hint">Cancelling needs the server's API token.</span>
						{/if}
					{/if}
					{#if cancelError}
						<Alert tone="danger">{cancelError}</Alert>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</section>

<style>
	.card {
		container-type: inline-size;
		display: flex;
		flex-direction: column;
		min-width: 0;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
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

	.card-body {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-5);
	}

	.job-head {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--space-4);
		min-width: 0;
	}

	.job-guild {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}

	.guild-name {
		font: var(--type-heading-md);
	}

	.job-meta {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.where {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
		max-width: 50%;
		font: var(--type-label-md);
		color: var(--text-secondary);
	}

	.where.live {
		color: var(--accent);
	}

	.live-dot {
		width: 8px;
		height: 8px;
		flex-shrink: 0;
		border-radius: var(--radius-full);
		background: var(--accent);
		animation: pulse var(--duration-shimmer) var(--ease-in-out) infinite;
	}

	.counters {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--space-3);
		padding: var(--space-4);
		background: var(--bg-raised);
		border-radius: var(--radius-sm);
	}

	.counter {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}

	.counter dt {
		order: 2;
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.counter dd {
		font: var(--type-mono-num-lg);
		font-size: 22px;
		line-height: 28px;
		color: var(--text-primary);
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.counter dd.muted {
		color: var(--text-tertiary);
	}

	.sub-title {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--space-3);
		margin-bottom: var(--space-2);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-secondary);
	}

	.sub-title .count {
		font: var(--type-mono-sm);
		text-transform: none;
		letter-spacing: 0;
		color: var(--text-tertiary);
	}

	.channels {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-2);
	}

	.channel-list {
		list-style: none;
		width: 100%;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
	}

	.channel-row {
		display: grid;
		grid-template-columns: 16px minmax(0, 1fr) auto 72px;
		align-items: center;
		gap: var(--space-3);
		height: 34px;
		padding: 0 var(--space-3);
		border-bottom: 1px solid var(--border-subtle);
		font: var(--type-body-sm);
	}

	.channel-row:last-child {
		border-bottom: none;
	}

	.channel-icon {
		display: inline-flex;
		color: var(--text-tertiary);
	}

	[data-state='done'] .channel-icon {
		color: var(--success);
	}

	[data-state='scraping'] .channel-icon {
		color: var(--accent);
		animation: pulse var(--duration-shimmer) var(--ease-in-out) infinite;
	}

	.channel-count {
		font: var(--type-mono-md);
		color: var(--text-secondary);
	}

	.channel-state {
		font: var(--type-label-xs);
		color: var(--text-tertiary);
		text-align: right;
	}

	[data-state='scraping'] .channel-state {
		color: var(--accent);
	}

	.warnings summary {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		cursor: pointer;
		font: var(--type-label-sm);
		color: var(--warning);
	}

	.warnings ul {
		list-style: none;
		margin-top: var(--space-2);
	}

	.warnings li {
		padding: var(--space-1) 0;
		border-bottom: 1px solid var(--border-subtle);
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.cancel {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-3);
		padding-top: var(--space-4);
		border-top: 1px solid var(--border-subtle);
	}

	.hint {
		font: var(--type-body-sm);
		color: var(--text-tertiary);
	}

	.confirm {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		width: 100%;
		padding: var(--space-3) var(--space-4);
		border: 1px solid color-mix(in srgb, var(--danger) 24%, transparent);
		border-radius: var(--radius-sm);
		background: color-mix(in srgb, var(--danger) 6%, transparent);
		animation: fade-in var(--duration-small) var(--ease-standard);
	}

	.confirm-text {
		flex: 1 1 240px;
		font: var(--type-body-sm);
	}

	.confirm-actions {
		display: flex;
		gap: var(--space-2);
	}

	@container (max-width: 480px) {
		.counters {
			grid-template-columns: repeat(2, 1fr);
		}

		.job-head {
			flex-direction: column;
			align-items: flex-start;
		}

		.where {
			max-width: 100%;
		}
	}
</style>
