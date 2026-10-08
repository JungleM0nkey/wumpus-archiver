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

	function statusColor(s: string): string {
		switch (s) {
			case 'completed': return 'var(--success)';
			case 'failed': return 'var(--danger)';
			case 'cancelled': return 'var(--warning)';
			case 'scraping':
			case 'connecting': return 'var(--accent)';
			default: return 'var(--text-tertiary)';
		}
	}

	function statusIcon(s: string): string {
		switch (s) {
			case 'completed': return '✓';
			case 'failed': return '✗';
			case 'cancelled': return '⊘';
			case 'scraping': return '◉';
			case 'connecting': return '◌';
			case 'pending': return '◌';
			default: return '·';
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
		<h1 class="panel-title">
			Control
		</h1>
		<p class="panel-sub">Run and monitor Discord server scrapes from here.</p>
	</header>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<span class="mono">Loading...</span>
		</div>
	{:else if error}
		<div class="error-state">
			<p>⚠ {error}</p>
		</div>
	{:else}
		<!-- Token Warning -->
		{#if !hasToken}
			<div class="alert alert-warning enter">
				<span class="alert-icon">⚠</span>
				<div>
					<strong>No Discord bot token configured.</strong>
					<p>Set <code>DISCORD_BOT_TOKEN</code> in your <code>.env</code> file and restart the server to enable scraping.</p>
				</div>
			</div>
		{/if}

		{#if !controlEnabled}
			<div class="alert alert-warning enter">
				<span class="alert-icon">⚠</span>
				<div>
					<strong>Scrape control is disabled.</strong>
					<p>Set <code>API_AUTH_TOKEN</code> in your <code>.env</code> file and restart the server, then enter it below to start or cancel scrapes.</p>
				</div>
			</div>
		{/if}

		<div class="panel-grid">
			<!-- Start Scrape Card -->
			<section class="card start-card enter">
				<div class="card-header">
					<h2 class="card-title">
						<span class="card-icon">▶</span>
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
								{#each guilds as guild}
									<option value={guild.id}>{guild.name} ({guild.id})</option>
								{/each}
							</select>
						{/if}
					</div>
					<div class="form-group">
						<label class="form-label" for="guild-id-input">Or enter Guild ID</label>
						<input
							id="guild-id-input"
							class="form-input"
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
							class="form-input"
							type="password"
							autocomplete="off"
							placeholder="API_AUTH_TOKEN"
							bind:value={apiToken}
							oninput={handleTokenInput}
						/>
						<p class="form-hint">Kept in this browser tab only (sessionStorage).</p>
					</div>

					{#if actionError}
						<div class="inline-error">{actionError}</div>
					{/if}

					<div class="card-actions">
						{#if isBusy}
							<button class="btn btn-danger" onclick={handleCancel}>
								⊘ Cancel Scrape
							</button>
						{:else}
							<button class="btn btn-primary" onclick={handleStart} disabled={!hasToken || !controlEnabled}>
								▶ Start Scrape
							</button>
						{/if}
					</div>
				</div>
			</section>

			<!-- Live Status Card -->
			<section class="card status-card enter">
				<div class="card-header">
					<h2 class="card-title">
						<span class="card-icon">◉</span>
						Live Status
					</h2>
					{#if currentJob}
						<span
							class="status-badge"
							style="color: {statusColor(currentJob.status)}"
						>
							{statusIcon(currentJob.status)} {currentJob.status}
						</span>
					{:else}
						<span class="status-badge" style="color: var(--text-tertiary)">
							· idle
						</span>
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
								<div class="progress-number">{currentJob.progress.channels_done.toLocaleString()}</div>
								<div class="progress-label">channels</div>
							</div>
							<div class="progress-stat">
								<div class="progress-number">{currentJob.progress.messages_scraped.toLocaleString()}</div>
								<div class="progress-label">messages</div>
							</div>
							<div class="progress-stat">
								<div class="progress-number">{currentJob.progress.attachments_found.toLocaleString()}</div>
								<div class="progress-label">attachments</div>
							</div>
						</div>

						{#if isBusy}
							<div class="pulse-bar">
								<div class="pulse-fill"></div>
							</div>
						{/if}

						{#if currentJob.error_message}
							<div class="inline-error" style="margin-top: var(--space-3)">
								{currentJob.error_message}
							</div>
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
						<div class="empty-status">
							<span class="empty-icon">◌</span>
							<p>No active scrape job. Start one from the left panel.</p>
						</div>
					{/if}
				</div>
			</section>
		</div>

		<!-- Download Stats -->
		{#if dlStats}
			<section class="downloads-section enter">
				<h2 class="section-title">
					<span class="section-icon">⬇</span>
					Downloaded Images
				</h2>

				<div class="dl-overview">
					<div class="dl-summary-grid">
						<div class="dl-stat">
							<div class="dl-stat-number">{dlStats.downloaded.toLocaleString()}</div>
							<div class="dl-stat-label">downloaded</div>
						</div>
						<div class="dl-stat">
							<div class="dl-stat-number">{dlStats.total_images.toLocaleString()}</div>
							<div class="dl-stat-label">total images</div>
						</div>
						<div class="dl-stat">
							<div class="dl-stat-number">{formatBytes(dlStats.downloaded_bytes)}</div>
							<div class="dl-stat-label">on disk</div>
						</div>
						<div class="dl-stat">
							<div class="dl-stat-number">{dlPercent(dlStats)}%</div>
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
							<span class="dl-tag dl-tag-pending">{dlStats.pending.toLocaleString()} pending</span>
						{/if}
						{#if dlStats.failed > 0}
							<span class="dl-tag dl-tag-failed">{dlStats.failed.toLocaleString()} failed</span>
						{/if}
						{#if dlStats.skipped > 0}
							<span class="dl-tag dl-tag-skipped">{dlStats.skipped.toLocaleString()} skipped</span>
						{/if}
						{#if dlStats.attachments_dir}
							<span class="dl-tag dl-tag-path mono" title={dlStats.attachments_dir}>📁 {dlStats.attachments_dir}</span>
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
													<span class="dl-cell-pct">{pct}%</span>
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
		<section class="history-section enter">
			<h2 class="section-title">
				<span class="section-icon">▤</span>
				Scrape History
			</h2>
			{#if history.length === 0}
				<div class="empty-history">
					<p class="mono" style="color: var(--text-tertiary)">No completed jobs yet.</p>
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
							{#each history as job}
								<tr>
									<td>
										<span class="table-status" style="color: {statusColor(job.status)}">
											{statusIcon(job.status)} {job.status}
										</span>
									</td>
									<td class="mono">{job.id}</td>
									<td class="mono">{job.guild_id}</td>
									<td>{job.progress.channels_done}</td>
									<td>{job.progress.messages_scraped.toLocaleString()}</td>
									<td>{job.progress.attachments_found.toLocaleString()}</td>
									<td class="mono">{formatDuration(job.duration_seconds)}</td>
									<td>{formatDate(job.started_at)}</td>
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
		padding: var(--space-8) var(--space-6);
	}

	/* Header */
	.panel-header {
		margin-bottom: var(--space-8);
	}

	.panel-title {
		font-size: 36px;
		font-weight: 700;
		letter-spacing: -0.03em;
		line-height: 1.1;
	}


	.panel-sub {
		margin-top: var(--space-2);
		color: var(--text-secondary);
		font-size: 15px;
	}

	/* Alert */
	.alert {
		display: flex;
		align-items: flex-start;
		gap: var(--space-3);
		padding: var(--space-4) var(--space-5);
		border-radius: var(--radius-md);
		margin-bottom: var(--space-6);
		font-size: 14px;
		line-height: 1.5;
	}

	.alert-warning {
		background: rgba(251, 191, 36, 0.08);
		border: 1px solid rgba(251, 191, 36, 0.2);
		color: var(--warning);
	}

	.alert-icon {
		font-size: 18px;
		flex-shrink: 0;
		margin-top: 1px;
	}

	.alert p {
		margin-top: var(--space-1);
		color: var(--text-secondary);
	}

	.alert code {
		font-family: var(--font-mono);
		font-size: 13px;
		padding: 1px 5px;
		background: var(--bg-overlay);
		border-radius: var(--radius-xs);
	}

	/* Grid */
	.panel-grid {
		display: grid;
		grid-template-columns: 1fr 1.4fr;
		gap: var(--space-6);
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

	.card-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-4) var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
	}

	.card-title {
		font-size: 15px;
		font-weight: 600;
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.card-icon {
		color: var(--accent);
		font-size: 14px;
	}

	.card-body {
		padding: var(--space-5);
	}

	/* Form */
	.form-group {
		margin-bottom: var(--space-4);
	}

	.form-label {
		display: block;
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		margin-bottom: var(--space-1);
	}

	.form-select,
	.form-input {
		width: 100%;
		padding: var(--space-2) var(--space-3);
		font-family: var(--font-mono);
		font-size: 14px;
		background: var(--bg-raised);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.form-select:focus,
	.form-input:focus {
		outline: none;
		border-color: var(--accent-strong);
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

	.form-hint {
		margin-top: var(--space-1);
		font-size: 12px;
		color: var(--text-tertiary);
	}

	.inline-error {
		font-size: 13px;
		color: var(--danger);
		padding: var(--space-2) var(--space-3);
		background: rgba(248, 113, 113, 0.08);
		border-radius: var(--radius-xs);
		margin-bottom: var(--space-3);
	}

	.card-actions {
		margin-top: var(--space-4);
		display: flex;
		gap: var(--space-3);
	}

	/* Buttons */
	.btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-5);
		font-size: 14px;
		font-weight: 600;
		border-radius: var(--radius-sm);
		transition: all var(--duration-micro) var(--ease-out-quint);
		cursor: pointer;
	}

	.btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--accent);
		color: var(--bg-canvas);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--accent-strong);
	}

	.btn-danger {
		background: rgba(248, 113, 113, 0.15);
		color: var(--danger);
		border: 1px solid rgba(248, 113, 113, 0.3);
	}

	.btn-danger:hover {
		background: rgba(248, 113, 113, 0.25);
	}

	/* Status Card */
	.status-badge {
		font-family: var(--font-mono);
		font-size: 12px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		display: flex;
		align-items: center;
		gap: var(--space-1);
	}

	.status-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-3);
		margin-bottom: var(--space-5);
	}

	.status-item {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.status-label {
		font-size: 11px;
		font-weight: 500;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.status-value {
		font-size: 14px;
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
		margin-bottom: var(--space-4);
	}

	.progress-stat {
		text-align: center;
	}

	.progress-number {
		font-family: var(--font-mono);
		font-size: 22px;
		font-weight: 700;
		color: var(--accent);
		line-height: 1.2;
	}

	.progress-label {
		font-size: 11px;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		margin-top: 2px;
	}

	/* Pulse Bar */
	.pulse-bar {
		height: 3px;
		background: var(--bg-raised);
		border-radius: 2px;
		overflow: hidden;
	}

	.pulse-fill {
		height: 100%;
		width: 40%;
		background: var(--accent);
		border-radius: 2px;
		animation: pulse 1.8s ease-in-out infinite;
	}

	@keyframes pulse {
		0% { transform: translateX(-100%); }
		100% { transform: translateX(350%); }
	}

	/* Error Details */
	.error-details {
		margin-top: var(--space-3);
		font-size: 13px;
	}

	.error-details summary {
		cursor: pointer;
		color: var(--warning);
		padding: var(--space-2);
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
		font-size: 12px;
	}

	/* Empty State */
	.empty-status {
		text-align: center;
		padding: var(--space-8) var(--space-4);
		color: var(--text-tertiary);
	}

	.empty-icon {
		font-size: 36px;
		display: block;
		margin-bottom: var(--space-3);
		opacity: 0.4;
	}

	/* Loading */
	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-16) 0;
		color: var(--text-tertiary);
	}

	.spinner {
		width: 24px;
		height: 24px;
		border: 2px solid var(--border-default);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.error-state {
		text-align: center;
		padding: var(--space-16) 0;
		color: var(--danger);
	}

	/* History Section */
	.history-section {
		margin-top: var(--space-2);
	}

	.section-title {
		font-size: 16px;
		font-weight: 600;
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}

	.section-icon {
		color: var(--accent);
	}

	.empty-history {
		padding: var(--space-6);
		text-align: center;
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
		font-size: 13px;
	}

	.history-table th {
		text-align: left;
		padding: var(--space-3) var(--space-4);
		font-size: 11px;
		font-weight: 600;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-raised);
		white-space: nowrap;
	}

	.history-table td {
		padding: var(--space-3) var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
		white-space: nowrap;
	}

	.history-table tr:last-child td {
		border-bottom: none;
	}

	.history-table tr:hover td {
		background: var(--bg-hover);
	}

	.table-status {
		font-family: var(--font-mono);
		font-size: 12px;
		font-weight: 600;
		display: flex;
		align-items: center;
		gap: 4px;
	}

	/* Downloads Section */
	.downloads-section {
		margin-bottom: var(--space-8);
	}

	.dl-overview {
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
		margin-bottom: var(--space-4);
	}

	@media (max-width: 600px) {
		.dl-summary-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	.dl-stat {
		text-align: center;
	}

	.dl-stat-number {
		font-family: var(--font-mono);
		font-size: 22px;
		font-weight: 700;
		color: var(--accent);
		line-height: 1.2;
	}

	.dl-stat-label {
		font-size: 11px;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		margin-top: 2px;
	}

	.dl-progress-bar {
		height: 6px;
		background: var(--bg-raised);
		border-radius: 3px;
		overflow: hidden;
		margin-bottom: var(--space-3);
	}

	.dl-progress-fill {
		height: 100%;
		background: var(--accent);
		border-radius: 3px;
		transition: width var(--duration-large) var(--ease-out-quint);
		min-width: 2px;
	}

	.dl-breakdown {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.dl-tag {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 2px 10px;
		font-size: 12px;
		border-radius: var(--radius-xs);
		font-weight: 500;
	}

	.dl-tag-pending {
		background: rgba(251, 191, 36, 0.1);
		color: var(--warning);
	}

	.dl-tag-failed {
		background: rgba(248, 113, 113, 0.1);
		color: var(--danger);
	}

	.dl-tag-skipped {
		background: rgba(148, 163, 184, 0.1);
		color: var(--text-secondary);
	}

	.dl-tag-path {
		background: var(--bg-raised);
		color: var(--text-secondary);
		max-width: 400px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 11px;
	}

	.dl-channels-details {
		margin-top: var(--space-2);
		font-size: 13px;
	}

	.dl-channels-details summary {
		cursor: pointer;
		color: var(--text-secondary);
		padding: var(--space-2) 0;
		font-size: 13px;
		user-select: none;
	}

	.dl-channels-details summary:hover {
		color: var(--text-primary);
	}

	.dl-channels-table-wrap {
		margin-top: var(--space-3);
		overflow-x: auto;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		background: var(--bg-surface);
		max-height: 400px;
		overflow-y: auto;
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
		border-radius: 2px;
		flex: 1;
		max-width: 60px;
	}

	.dl-cell-pct {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-tertiary);
		min-width: 32px;
		text-align: right;
	}
</style>
