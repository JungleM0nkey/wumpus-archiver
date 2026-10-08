<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getGuilds,
		getScrapeStatus,
		startScrape,
		cancelScrape,
		getScrapeHistory,
		getDownloadStats,
		getApiToken,
		setApiToken,
		ApiError
	} from '#lib/api.ts';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import Button from '#lib/components/ui/Button.svelte';
	import EmptyState from '#lib/components/ui/EmptyState.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';
	import type { IconName } from '#lib/components/ui/icons.ts';
	import type { Guild, ScrapeJob, ScrapeStatusResponse, ScrapeHistoryResponse, DownloadStatsResponse } from '#lib/types.ts';

	let guilds: Guild[] = $state([]);
	let status = $state<ScrapeStatusResponse | null>(null);
	let history: ScrapeJob[] = $state([]);
	let dlStats: DownloadStatsResponse | null = $state(null);
	let loading = $state(true);
	let error = $state('');
	let actionError = $state('');
	let selectedGuildId = $state('');
	let customGuildId = $state('');
	let apiToken = $state('');

	// Computed
	let currentJob = $derived(status?.current_job ?? null);
	let isBusy = $derived(status?.busy ?? false);
	let hasToken = $derived(status?.has_token ?? false);
	let controlEnabled = $derived(status?.control_enabled ?? false);

	let resolvedGuildId = $derived(() => {
		if (customGuildId.trim()) return Number(customGuildId.trim());
		if (selectedGuildId) return Number(selectedGuildId);
		return null;
	});

	onMount(async () => {
		apiToken = getApiToken();
		await loadAll();
	});

	// Poll the scrape job's status every 2s, only while one is running.
	$effect(() => {
		if (!isBusy) return;
		const timer = setInterval(pollStatus, 2000);
		return () => clearInterval(timer);
	});

	async function loadAll() {
		try {
			const [g, s, h, dl] = await Promise.all([
				getGuilds().catch(() => []),
				getScrapeStatus(),
				getScrapeHistory(),
				getDownloadStats().catch(() => null)
			]);
			guilds = g;
			status = s;
			history = h.jobs;
			dlStats = dl;
			if (guilds.length > 0 && !selectedGuildId) {
				selectedGuildId = guilds[0].id;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load';
		} finally {
			loading = false;
		}
	}

	/** Read the status; when the job that was running (`jobRan`) has finished, re-read history. */
	async function refreshStatus(jobRan: boolean) {
		status = await getScrapeStatus();
		if (jobRan && !status.busy) {
			const hist = await getScrapeHistory();
			history = hist.jobs;
		}
	}

	async function pollStatus() {
		try {
			await refreshStatus(isBusy);
		} catch {
			// A failed poll is retried on the next tick
		}
	}

	function handleTokenInput() {
		setApiToken(apiToken.trim());
	}

	function describeActionError(e: unknown, fallback: string): string {
		if (e instanceof ApiError && e.status === 401) {
			return "Invalid or missing API token. Enter the server's API_AUTH_TOKEN above.";
		}
		if (e instanceof ApiError && e.status === 403) {
			return 'Scrape control is disabled on the server. Set API_AUTH_TOKEN and restart it.';
		}
		return e instanceof Error ? e.message : fallback;
	}

	async function handleStart() {
		actionError = '';
		const gid = resolvedGuildId();
		if (!gid) {
			actionError = 'Please select or enter a guild ID';
			return;
		}
		try {
			await startScrape(gid);
			await refreshStatus(true);
		} catch (e) {
			actionError = describeActionError(e, 'Failed to start scrape');
		}
	}

	async function handleCancel() {
		actionError = '';
		try {
			await cancelScrape();
			await refreshStatus(true);
		} catch (e) {
			actionError = describeActionError(e, 'Failed to cancel');
		}
	}

	function formatDuration(seconds: number | null): string {
		if (seconds === null) return '—';
		if (seconds < 60) return `${seconds.toFixed(1)}s`;
		const m = Math.floor(seconds / 60);
		const s = (seconds % 60).toFixed(0);
		return `${m}m ${s}s`;
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		});
	}

	type Tone = 'neutral' | 'accent' | 'success' | 'danger' | 'warning';

	function statusTone(s: string): Tone {
		switch (s) {
			case 'completed': return 'success';
			case 'failed': return 'danger';
			case 'cancelled': return 'warning';
			case 'scraping':
			case 'connecting': return 'accent';
			default: return 'neutral';
		}
	}

	function statusIcon(s: string): IconName {
		switch (s) {
			case 'completed': return 'circle-check';
			case 'failed': return 'circle-x';
			case 'cancelled': return 'ban';
			case 'scraping': return 'circle-dot';
			case 'connecting':
			case 'pending': return 'circle-dashed';
			default: return 'circle';
		}
	}

	function formatBytes(bytes: number): string {
		if (bytes === 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB', 'TB'];
		const i = Math.floor(Math.log(bytes) / Math.log(1024));
		const val = bytes / Math.pow(1024, i);
		return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
	}

	function dlPercent(dl: DownloadStatsResponse): number {
		if (dl.total_images === 0) return 0;
		return Math.round((dl.downloaded / dl.total_images) * 100);
	}
</script>

<div class="control-panel">
	<header class="panel-header">
		<h1 class="panel-title">Control</h1>
		<p class="panel-sub">Run and monitor Discord server scrapes from here.</p>
	</header>

	{#if loading}
		<div class="panel-grid" aria-busy="true">
			<span class="sr-only" role="status">Loading…</span>
			{#each [0, 1] as i (i)}
				<div class="card skeleton-card">
					<Skeleton width="40%" height="16px" />
					<Skeleton height="36px" radius="sm" />
					<Skeleton height="36px" radius="sm" />
					<Skeleton width="30%" height="36px" radius="sm" />
				</div>
			{/each}
		</div>
	{:else if error}
		<Alert tone="danger" title="Scrape control could not be loaded">{error}</Alert>
	{:else}
		<div class="alerts">
			{#if !hasToken}
				<Alert tone="warning" title="No Discord bot token configured.">
					Set <code>DISCORD_BOT_TOKEN</code> in your <code>.env</code> file and restart the server to enable scraping.
				</Alert>
			{/if}

			{#if !controlEnabled}
				<Alert tone="warning" title="Scrape control is disabled.">
					Set <code>API_AUTH_TOKEN</code> in your <code>.env</code> file and restart the server, then enter it below to start or cancel scrapes.
				</Alert>
			{/if}
		</div>

		<div class="panel-grid">
			<!-- Start Scrape Card -->
			<section class="card enter">
				<div class="card-header">
					<h2 class="card-title">
						<Icon name="play" />
						Start Scrape
					</h2>
				</div>
				<div class="card-body">
					<div class="form-group">
						<label class="form-label" for="guild-select">Guild</label>
						{#if guilds.length > 0}
							<select
								id="guild-select"
								class="form-select"
								bind:value={selectedGuildId}
								disabled={isBusy || !hasToken}
							>
								{#each guilds as guild (guild.id)}
									<option value={guild.id}>{guild.name} ({guild.id})</option>
								{/each}
							</select>
						{/if}
					</div>
					<div class="form-group">
						<label class="form-label" for="guild-id-input">Or enter Guild ID</label>
						<input
							id="guild-id-input"
							class="form-input mono"
							type="text"
							placeholder="e.g. 165682173540696064"
							bind:value={customGuildId}
							disabled={isBusy || !hasToken}
						/>
					</div>

					<div class="form-group">
						<label class="form-label" for="api-token-input">API token</label>
						<input
							id="api-token-input"
							class="form-input mono"
							type="password"
							autocomplete="off"
							placeholder="API_AUTH_TOKEN"
							bind:value={apiToken}
							oninput={handleTokenInput}
						/>
						<p class="form-hint">Kept in this browser tab only (sessionStorage).</p>
					</div>

					{#if actionError}
						<Alert tone="danger">{actionError}</Alert>
					{/if}

					<div class="card-actions">
						{#if isBusy}
							<Button variant="danger" icon="ban" onclick={handleCancel}>Cancel Scrape</Button>
						{:else}
							<Button
								variant="primary"
								icon="play"
								onclick={handleStart}
								disabled={!hasToken || !controlEnabled}
							>
								Start Scrape
							</Button>
						{/if}
					</div>
				</div>
			</section>

			<!-- Live Status Card -->
			<section class="card enter" style:--i={1}>
				<div class="card-header">
					<h2 class="card-title">
						<Icon name="activity" />
						Live Status
					</h2>
					{#if currentJob}
						<Badge tone={statusTone(currentJob.status)} icon={statusIcon(currentJob.status)}>
							{currentJob.status}
						</Badge>
					{:else}
						<Badge icon="circle">idle</Badge>
					{/if}
				</div>
				<div class="card-body">
					{#if currentJob}
						<div class="status-grid">
							<div class="status-item">
								<span class="status-label">Job ID</span>
								<span class="status-value mono">{currentJob.id}</span>
							</div>
							<div class="status-item">
								<span class="status-label">Guild</span>
								<span class="status-value mono">{currentJob.guild_id}</span>
							</div>
							<div class="status-item">
								<span class="status-label">Duration</span>
								<span class="status-value mono">{formatDuration(currentJob.duration_seconds)}</span>
							</div>
							<div class="status-item">
								<span class="status-label">Channel</span>
								<span class="status-value">{currentJob.progress.current_channel || '—'}</span>
							</div>
						</div>

						<div class="progress-stats">
							<div class="progress-stat">
								<div class="progress-number mono">{currentJob.progress.channels_done.toLocaleString()}</div>
								<div class="progress-label">channels</div>
							</div>
							<div class="progress-stat">
								<div class="progress-number mono">{currentJob.progress.messages_scraped.toLocaleString()}</div>
								<div class="progress-label">messages</div>
							</div>
							<div class="progress-stat">
								<div class="progress-number mono">{currentJob.progress.attachments_found.toLocaleString()}</div>
								<div class="progress-label">attachments</div>
							</div>
						</div>

						{#if isBusy}
							<div class="pulse-bar" role="progressbar" aria-label="Scraping">
								<div class="pulse-fill"></div>
							</div>
						{/if}

						{#if currentJob.error_message}
							<Alert tone="danger">{currentJob.error_message}</Alert>
						{/if}

						{#if currentJob.progress.errors.length > 0}
							<details class="error-details">
								<summary class="mono">{currentJob.progress.errors.length} warning(s)</summary>
								<ul class="error-list">
									{#each currentJob.progress.errors as err}
										<li>{err}</li>
									{/each}
								</ul>
							</details>
						{/if}
					{:else}
						<EmptyState
							icon="circle-dashed"
							title="No active scrape job."
							description="Start one from the left panel."
							compact
						/>
					{/if}
				</div>
			</section>
		</div>

		<!-- Download Stats -->
		{#if dlStats}
			<section class="downloads-section enter" style:--i={2}>
				<h2 class="section-title">
					<Icon name="download" />
					Downloaded Images
				</h2>

				<div class="dl-overview">
					<div class="dl-summary-grid">
						<div class="dl-stat">
							<div class="dl-stat-number mono">{dlStats.downloaded.toLocaleString()}</div>
							<div class="dl-stat-label">downloaded</div>
						</div>
						<div class="dl-stat">
							<div class="dl-stat-number mono">{dlStats.total_images.toLocaleString()}</div>
							<div class="dl-stat-label">total images</div>
						</div>
						<div class="dl-stat">
							<div class="dl-stat-number mono">{formatBytes(dlStats.downloaded_bytes)}</div>
							<div class="dl-stat-label">on disk</div>
						</div>
						<div class="dl-stat">
							<div class="dl-stat-number mono">{dlPercent(dlStats)}%</div>
							<div class="dl-stat-label">complete</div>
						</div>
					</div>

					<!-- Progress bar -->
					<div class="dl-progress-bar">
						<div
							class="dl-progress-fill"
							style="width: {dlPercent(dlStats)}%"
						></div>
					</div>

					<div class="dl-breakdown">
						{#if dlStats.pending > 0}
							<Badge tone="warning" mono>{dlStats.pending.toLocaleString()} pending</Badge>
						{/if}
						{#if dlStats.failed > 0}
							<Badge tone="danger" mono>{dlStats.failed.toLocaleString()} failed</Badge>
						{/if}
						{#if dlStats.skipped > 0}
							<Badge mono>{dlStats.skipped.toLocaleString()} skipped</Badge>
						{/if}
						{#if dlStats.attachments_dir}
							<Badge icon="folder" mono title={dlStats.attachments_dir}>{dlStats.attachments_dir}</Badge>
						{/if}
					</div>
				</div>

				{#if dlStats.channels.length > 0}
					<details class="dl-channels-details">
						<summary class="mono">Per-channel breakdown ({dlStats.channels.length} channels)</summary>
						<div class="dl-channels-table-wrap">
							<table class="history-table dl-channels-table">
								<thead>
									<tr>
										<th>Channel</th>
										<th>Downloaded</th>
										<th>Pending</th>
										<th>Failed</th>
										<th>Total</th>
										<th>Size</th>
										<th>Progress</th>
									</tr>
								</thead>
								<tbody>
									{#each dlStats.channels as ch}
										{@const pct = ch.total_images > 0 ? Math.round((ch.downloaded / ch.total_images) * 100) : 0}
										<tr>
											<td>#{ch.channel_name}</td>
											<td class="mono">{ch.downloaded.toLocaleString()}</td>
											<td class="mono">{ch.pending > 0 ? ch.pending.toLocaleString() : '—'}</td>
											<td class="mono" style:color={ch.failed > 0 ? 'var(--danger)' : undefined}>{ch.failed > 0 ? ch.failed.toLocaleString() : '—'}</td>
											<td class="mono">{ch.total_images.toLocaleString()}</td>
											<td class="mono">{formatBytes(ch.downloaded_bytes)}</td>
											<td>
												<div class="dl-cell-bar">
													<div class="dl-cell-fill" style="width: {pct}%"></div>
													<span class="dl-cell-pct mono">{pct}%</span>
												</div>
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</details>
				{/if}
			</section>
		{/if}

		<!-- History -->
		<section class="history-section enter" style:--i={3}>
			<h2 class="section-title">
				<Icon name="history" />
				Scrape History
			</h2>
			{#if history.length === 0}
				<div class="history-table-wrap">
					<EmptyState icon="history" title="No completed jobs yet." compact />
				</div>
			{:else}
				<div class="history-table-wrap">
					<table class="history-table">
						<thead>
							<tr>
								<th>Status</th>
								<th>Job ID</th>
								<th>Guild</th>
								<th>Channels</th>
								<th>Messages</th>
								<th>Attachments</th>
								<th>Duration</th>
								<th>Started</th>
							</tr>
						</thead>
						<tbody>
							{#each history as job (job.id)}
								<tr>
									<td>
										<Badge tone={statusTone(job.status)} icon={statusIcon(job.status)}>{job.status}</Badge>
									</td>
									<td class="mono">{job.id}</td>
									<td class="mono">{job.guild_id}</td>
									<td class="mono">{job.progress.channels_done}</td>
									<td class="mono">{job.progress.messages_scraped.toLocaleString()}</td>
									<td class="mono">{job.progress.attachments_found.toLocaleString()}</td>
									<td class="mono">{formatDuration(job.duration_seconds)}</td>
									<td class="mono">{formatDate(job.started_at)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{/if}
</div>

<style>
	.control-panel {
		max-width: 1200px;
		margin: 0 auto;
		padding: var(--space-10) var(--space-6);
	}

	/* Header */
	.panel-header {
		margin-bottom: var(--space-8);
	}

	.panel-title {
		font: var(--type-display-lg);
		letter-spacing: var(--tracking-display-lg);
	}

	.panel-sub {
		margin-top: var(--space-2);
		font: var(--type-body-md);
		color: var(--text-secondary);
	}

	.alerts {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin-bottom: var(--space-6);
	}

	.alerts:empty {
		display: none;
	}

	/* Grid */
	.panel-grid {
		display: grid;
		grid-template-columns: 1fr 1.4fr;
		gap: var(--space-4);
		margin-bottom: var(--space-8);
	}

	@media (max-width: 768px) {
		.panel-grid {
			grid-template-columns: 1fr;
		}
	}

	/* Cards */
	.card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	.skeleton-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-5);
	}

	.card-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-5);
		min-height: 52px;
		border-bottom: 1px solid var(--border-subtle);
	}

	.card-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-heading-sm);
	}

	.card-title :global(.icon),
	.section-title :global(.icon) {
		color: var(--text-secondary);
	}

	.card-body {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-5);
	}

	/* Form */
	.form-label {
		display: block;
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-secondary);
		margin-bottom: var(--space-1);
	}

	.form-select,
	.form-input {
		width: 100%;
		height: 36px;
		padding: 0 var(--space-3);
		font-size: 13px;
		background: var(--bg-raised);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.form-select {
		font: var(--type-label-md);
	}

	.form-select:hover:not(:disabled),
	.form-input:hover:not(:disabled) {
		border-color: var(--border-strong);
	}

	.form-select:focus-visible,
	.form-input:focus-visible {
		border-color: var(--accent-glow);
		outline-offset: 0;
	}

	.form-select:disabled,
	.form-input:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.form-select option {
		background: var(--bg-raised);
		color: var(--text-primary);
	}

	.form-input::placeholder {
		color: var(--text-tertiary);
	}

	.form-hint {
		margin-top: var(--space-1);
		font: var(--type-body-sm);
		color: var(--text-tertiary);
	}

	.card-actions {
		display: flex;
		gap: var(--space-3);
	}

	/* Status Card */
	.status-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-3);
	}

	.status-item {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}

	.status-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	.status-value {
		font-size: 13px;
		line-height: 18px;
		color: var(--text-primary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* Progress Stats */
	.progress-stats {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: var(--space-4);
		padding: var(--space-4);
		background: var(--bg-raised);
		border-radius: var(--radius-sm);
	}

	.progress-stat,
	.dl-stat {
		text-align: center;
	}

	.progress-number,
	.dl-stat-number {
		font: var(--type-mono-num-lg);
		font-size: 22px;
		line-height: 28px;
		color: var(--text-primary);
	}

	.progress-label,
	.dl-stat-label {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
		margin-top: 2px;
	}

	/* Indeterminate progress while a job runs */
	.pulse-bar {
		height: 3px;
		background: var(--bg-raised);
		border-radius: var(--radius-full);
		overflow: hidden;
	}

	.pulse-fill {
		height: 100%;
		width: 40%;
		background: var(--accent);
		border-radius: var(--radius-full);
		animation: sweep 1.8s var(--ease-in-out) infinite;
	}

	/* Error Details */
	.error-details {
		font: var(--type-body-sm);
	}

	.error-details summary {
		cursor: pointer;
		color: var(--warning);
		padding: var(--space-2) 0;
		font: var(--type-mono-sm);
	}

	.error-list {
		list-style: none;
		padding: var(--space-2) var(--space-3);
		max-height: 200px;
		overflow-y: auto;
	}

	.error-list li {
		padding: var(--space-1) 0;
		color: var(--text-secondary);
		border-bottom: 1px solid var(--border-subtle);
		font: var(--type-body-sm);
	}

	/* Sections */
	.section-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-heading-md);
		margin-bottom: var(--space-4);
	}

	.history-table-wrap {
		overflow-x: auto;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		background: var(--bg-surface);
	}

	.history-table {
		width: 100%;
		border-collapse: collapse;
		font: var(--type-body-sm);
	}

	.history-table th {
		text-align: left;
		padding: var(--space-3) var(--space-4);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-raised);
		white-space: nowrap;
	}

	.history-table td {
		padding: var(--space-3) var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
		white-space: nowrap;
	}

	.history-table td.mono {
		font-size: 12px;
	}

	.history-table tr:last-child td {
		border-bottom: none;
	}

	.history-table tbody tr:hover td {
		background: var(--bg-hover);
	}

	/* Downloads Section */
	.downloads-section {
		margin-bottom: var(--space-8);
	}

	.dl-overview {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		padding: var(--space-5);
		margin-bottom: var(--space-4);
	}

	.dl-summary-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--space-4);
		padding: var(--space-4);
		background: var(--bg-raised);
		border-radius: var(--radius-sm);
	}

	@media (max-width: 600px) {
		.dl-summary-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	.dl-progress-bar {
		height: 6px;
		background: var(--bg-raised);
		border-radius: var(--radius-full);
		overflow: hidden;
	}

	.dl-progress-fill {
		height: 100%;
		background: var(--accent);
		border-radius: var(--radius-full);
		min-width: 2px;
	}

	.dl-breakdown {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		min-width: 0;
	}

	.dl-channels-details summary {
		cursor: pointer;
		color: var(--text-secondary);
		padding: var(--space-2) 0;
		font: var(--type-mono-sm);
		user-select: none;
	}

	.dl-channels-details summary:hover {
		color: var(--text-primary);
	}

	.dl-channels-table-wrap {
		margin-top: var(--space-3);
		overflow: auto;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		background: var(--bg-surface);
		max-height: 400px;
	}

	.dl-cell-bar {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 80px;
	}

	.dl-cell-bar .dl-cell-fill {
		height: 4px;
		background: var(--accent);
		border-radius: var(--radius-full);
		flex: 1;
		max-width: 60px;
	}

	.dl-cell-pct {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		min-width: 32px;
		text-align: right;
	}
</style>
