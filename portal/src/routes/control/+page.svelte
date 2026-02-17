<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		getGuilds,
		getScrapeStatus,
		startScrape,
		cancelScrape,
		getScrapeHistory,
		getDownloadStats,
		startDownload,
		getDownloadJobStatus,
		cancelDownload,
		analyzeGuild,
		getTransferStatus,
		startTransfer,
		cancelTransfer,
		getDataSource
	} from '$lib/api';
	import type {
		Guild,
		ScrapeJob,
		ScrapeStatusResponse,
		ScrapeHistoryResponse,
		DownloadStatsResponse,
		DownloadJobStatus,
		AnalyzeResponse,
		AnalyzeChannel,
		TransferStatus,
		DataSourceResponse
	} from '$lib/types';

	// --- Core state ---
	let guilds: Guild[] = $state([]);
	let status: ScrapeStatusResponse | null = $state(null);
	let history: ScrapeJob[] = $state([]);
	let dlStats: DownloadStatsResponse | null = $state(null);
	let loading = $state(true);
	let error = $state('');
	let actionError = $state('');
	let selectedGuildId = $state('');
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	// --- Analyze state ---
	let analyzeResult: AnalyzeResponse | null = $state(null);
	let analyzing = $state(false);
	let analyzeError = $state('');

	// --- Channel selection state ---
	let selectedChannelIds: Set<string> = $state(new Set());
	let collapsedCategories: Set<string> = $state(new Set());
	let channelFilter = $state('');

	// --- Transfer state ---
	let transferStatus: TransferStatus | null = $state(null);
	let datasourceInfo: DataSourceResponse | null = $state(null);
	let transferError = $state('');
	let transferPollTimer: ReturnType<typeof setInterval> | null = null;

	// --- Download job state ---
	let downloadJob: DownloadJobStatus | null = $state(null);
	let downloadError = $state('');
	let downloadPollTimer: ReturnType<typeof setInterval> | null = null;

	// --- Utilities drawer ---
	let utilitiesOpen = $state(false);

	// --- Derived ---
	let currentJob = $derived(status?.current_job ?? null);
	let isBusy = $derived(status?.busy ?? false);
	let hasToken = $derived(status?.has_token ?? false);
	let selectedGuild = $derived(guilds.find(g => g.id === selectedGuildId));

	let selectedCount = $derived(selectedChannelIds.size);

	let showTransfer = $derived(
		datasourceInfo !== null &&
		Object.entries(datasourceInfo.sources).filter(([, info]) => info.available !== false).length >= 2
	);
	let transferBusy = $derived(
		transferStatus?.status === 'pending' || transferStatus?.status === 'running'
	);
	let transferPercent = $derived.by(() => {
		if (!transferStatus || transferStatus.total_rows === 0) return 0;
		return Math.round((transferStatus.rows_transferred / transferStatus.total_rows) * 100);
	});

	// Phase logic: what state is the primary panel in?
	type Phase = 'idle' | 'analyzing' | 'analyzed' | 'scraping' | 'completed' | 'failed';
	let phase: Phase = $derived.by(() => {
		if (analyzing) return 'analyzing';
		if (isBusy && currentJob) {
			if (currentJob.status === 'completed') return 'completed';
			if (currentJob.status === 'failed') return 'failed';
			return 'scraping';
		}
		if (currentJob && (currentJob.status === 'completed' || currentJob.status === 'failed' || currentJob.status === 'cancelled')) {
			if (!analyzeResult) return 'idle';
		}
		if (analyzeResult) return 'analyzed';
		return 'idle';
	});

	// Channel grouping — uses analyzeResult.channels directly
	let analyzeChannels = $derived(analyzeResult?.channels ?? []);
	let groupedChannels = $derived.by(() => {
		const groups = new Map<string, AnalyzeChannel[]>();
		const filtered = channelFilter.trim()
			? analyzeChannels.filter(c =>
				c.name.toLowerCase().includes(channelFilter.trim().toLowerCase())
			)
			: analyzeChannels;
		for (const ch of filtered) {
			const cat = ch.parent_name ?? '(no category)';
			if (!groups.has(cat)) groups.set(cat, []);
			groups.get(cat)!.push(ch);
		}
		return groups;
	});

	// Analyze summary helpers
	let needsScrapeCount = $derived.by(() => {
		if (!analyzeResult) return 0;
		const s = analyzeResult.summary;
		return (s.new ?? 0) + (s.has_new_messages ?? 0) + (s.never_scraped ?? 0);
	});

	$effect(() => {
		if (transferBusy) startTransferPolling();
	});

	// --- Functions ---

	async function handleAnalyze() {
		if (!selectedGuildId) {
			analyzeError = 'Select a guild first';
			return;
		}
		analyzing = true;
		analyzeError = '';
		analyzeResult = null;
		actionError = '';
		try {
			const result = await analyzeGuild(selectedGuildId);
			analyzeResult = result;

			// Pre-select channels that need scraping
			const needsScrape = new Set(
				result.channels
					.filter(ch => ch.status === 'new' || ch.status === 'has_new_messages' || ch.status === 'never_scraped')
					.map(ch => ch.id)
			);
			selectedChannelIds = needsScrape;
		} catch (e) {
			analyzeError = e instanceof Error ? e.message : 'Failed to analyze guild';
		} finally {
			analyzing = false;
		}
	}

	function toggleChannel(id: string) {
		const next = new Set(selectedChannelIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selectedChannelIds = next;
	}

	function selectAllVisible() {
		const visible = channelFilter.trim()
			? analyzeChannels.filter(c =>
				c.name.toLowerCase().includes(channelFilter.trim().toLowerCase())
			)
			: analyzeChannels;
		const next = new Set(selectedChannelIds);
		for (const c of visible) next.add(c.id);
		selectedChannelIds = next;
	}

	function deselectAllVisible() {
		if (!channelFilter.trim()) {
			selectedChannelIds = new Set();
			return;
		}
		const filtered = new Set(
			analyzeChannels
				.filter((c: AnalyzeChannel) => c.name.toLowerCase().includes(channelFilter.trim().toLowerCase()))
				.map((c: AnalyzeChannel) => c.id)
		);
		selectedChannelIds = new Set([...selectedChannelIds].filter(id => !filtered.has(id)));
	}

	function selectNeedsScrape() {
		if (!analyzeResult) return;
		const ids = new Set(
			analyzeResult.channels
				.filter(ch => ch.status !== 'up_to_date')
				.map(ch => ch.id)
		);
		selectedChannelIds = ids;
	}

	function toggleCategory(cat: string) {
		const next = new Set(collapsedCategories);
		if (next.has(cat)) next.delete(cat);
		else next.add(cat);
		collapsedCategories = next;
	}

	function channelIcon(type: number): string {
		switch (type) {
			case 0: return '#';
			case 2: return '~';
			case 5: return '!';
			case 11:
			case 12: return '/';
			case 13: return '~';
			case 15: return '=';
			default: return '#';
		}
	}

	async function handleStart() {
		actionError = '';
		if (!selectedGuildId) {
			actionError = 'Select a guild first';
			return;
		}
		try {
			if (selectedChannelIds.size > 0) {
				await startScrape(selectedGuildId, Array.from(selectedChannelIds));
			} else {
				await startScrape(selectedGuildId);
			}
			status = await getScrapeStatus();
			const hist = await getScrapeHistory();
			history = hist.jobs;
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Failed to start scrape';
		}
	}

	async function handleCancel() {
		actionError = '';
		try {
			await cancelScrape();
			status = await getScrapeStatus();
			const hist = await getScrapeHistory();
			history = hist.jobs;
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Failed to cancel';
		}
	}

	function handleReset() {
		analyzeResult = null;
		analyzeError = '';
		actionError = '';
		selectedChannelIds = new Set();
		channelFilter = '';
	}

	onMount(async () => {
		await loadAll();
		pollTimer = setInterval(pollStatus, 2000);
	});

	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
		stopTransferPolling();
		stopDownloadPolling();
	});

	async function loadAll() {
		try {
			const [g, s, h, dl, dj] = await Promise.all([
				getGuilds().catch(() => []),
				getScrapeStatus(),
				getScrapeHistory(),
				getDownloadStats().catch(() => null),
				getDownloadJobStatus().catch(() => null)
			]);
			guilds = g;
			status = s;
			history = h.jobs;
			dlStats = dl;
			downloadJob = dj;
			if (dj && (dj.status === 'pending' || dj.status === 'running')) {
				startDownloadPolling();
			}
			await loadTransferInfo();
			if (guilds.length > 0 && !selectedGuildId) {
				selectedGuildId = guilds[0].id;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load';
		} finally {
			loading = false;
		}
	}

	async function pollStatus() {
		try {
			const prev = status;
			status = await getScrapeStatus();
			// Refresh history when scrape finishes (busy → not busy) or when idle
			if (status && !status.busy && (prev?.busy || history.length === 0)) {
				const hist = await getScrapeHistory();
				history = hist.jobs;
				// Also refresh download stats since scrape may have added new attachments
				dlStats = await getDownloadStats().catch(() => dlStats);
			}
		} catch {
			// Silently fail polling
		}
	}

	async function loadTransferInfo() {
		try {
			const [ds, ts] = await Promise.all([
				getDataSource().catch(() => null),
				getTransferStatus().catch(() => null)
			]);
			datasourceInfo = ds;
			transferStatus = ts;
		} catch {
			// Silently fail
		}
	}

	async function handleStartTransfer() {
		transferError = '';
		try {
			await startTransfer();
			transferStatus = await getTransferStatus();
			startTransferPolling();
		} catch (e) {
			transferError = e instanceof Error ? e.message : 'Failed to start transfer';
		}
	}

	async function handleCancelTransfer() {
		transferError = '';
		try {
			await cancelTransfer();
			transferStatus = await getTransferStatus();
		} catch (e) {
			transferError = e instanceof Error ? e.message : 'Failed to cancel transfer';
		}
	}

	function startTransferPolling() {
		if (transferPollTimer) return;
		transferPollTimer = setInterval(async () => {
			try {
				transferStatus = await getTransferStatus();
				if (transferStatus && !['pending', 'running'].includes(transferStatus.status)) {
					stopTransferPolling();
				}
			} catch {
				// Silently fail
			}
		}, 1000);
	}

	function stopTransferPolling() {
		if (transferPollTimer) {
			clearInterval(transferPollTimer);
			transferPollTimer = null;
		}
	}

	// --- Download job handlers ---

	let isDownloading = $derived(
		downloadJob != null && (downloadJob.status === 'pending' || downloadJob.status === 'running')
	);

	async function handleStartDownload() {
		downloadError = '';
		try {
			downloadJob = await startDownload();
			startDownloadPolling();
		} catch (e) {
			downloadError = e instanceof Error ? e.message : 'Failed to start download';
		}
	}

	async function handleCancelDownload() {
		try {
			await cancelDownload();
			downloadJob = await getDownloadJobStatus();
		} catch (e) {
			downloadError = e instanceof Error ? e.message : 'Failed to cancel';
		}
	}

	function startDownloadPolling() {
		stopDownloadPolling();
		downloadPollTimer = setInterval(async () => {
			try {
				downloadJob = await getDownloadJobStatus();
				if (downloadJob && !isDownloading) {
					stopDownloadPolling();
					// Refresh download stats when done
					dlStats = await getDownloadStats().catch(() => dlStats);
				}
			} catch {
				// Silently fail
			}
		}, 2000);
	}

	function stopDownloadPolling() {
		if (downloadPollTimer) {
			clearInterval(downloadPollTimer);
			downloadPollTimer = null;
		}
	}

	function formatDuration(seconds: number | null): string {
		if (seconds === null) return '--';
		if (seconds < 60) return `${seconds.toFixed(1)}s`;
		const m = Math.floor(seconds / 60);
		const s = (seconds % 60).toFixed(0);
		return `${m}m ${s}s`;
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '--';
		return new Date(iso).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		});
	}

	function timeAgo(iso: string | null): string {
		if (!iso) return 'never';
		const diff = Date.now() - new Date(iso).getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 60) return `${mins}m ago`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	function statusColor(s: string): string {
		switch (s) {
			case 'completed': return 'var(--success)';
			case 'failed': return 'var(--error)';
			case 'cancelled': return 'var(--warning)';
			case 'scraping':
			case 'connecting':
			case 'running': return 'var(--accent)';
			default: return 'var(--text-muted)';
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

<div class="control">
	<header class="page-header">
		<h1 class="page-title serif">Control<span class="dot">.</span></h1>
	</header>

	{#if loading}
		<div class="center-state">
			<div class="spinner"></div>
			<span class="mono">Loading...</span>
		</div>
	{:else if error}
		<div class="center-state">
			<p style="color: var(--error)">Failed to load: {error}</p>
		</div>
	{:else}
		<!-- Primary Panel -->
		<div class="primary-panel fade-in">

			{#if !hasToken}
				<div class="panel-alert">
					No Discord bot token configured. Set <code>DISCORD_BOT_TOKEN</code> in .env and restart.
				</div>
			{/if}

			<!-- ─── IDLE: Guild selector + archive health ─── -->
			{#if phase === 'idle'}
				<div class="phase-idle">
					<div class="guild-row">
						<label class="label" for="guild-sel">Guild</label>
						<select id="guild-sel" class="guild-select" bind:value={selectedGuildId} disabled={!hasToken}>
							{#each guilds as guild}
								<option value={guild.id}>{guild.name}</option>
							{/each}
						</select>
					</div>

					{#if selectedGuild}
						<div class="health-strip">
							<div class="health-stat">
								<span class="health-val mono">{selectedGuild.message_count.toLocaleString()}</span>
								<span class="health-lbl">messages</span>
							</div>
							<div class="health-stat">
								<span class="health-val mono">{selectedGuild.channel_count}</span>
								<span class="health-lbl">channels</span>
							</div>
							<div class="health-stat">
								<span class="health-val mono">{timeAgo(selectedGuild.last_scraped_at)}</span>
								<span class="health-lbl">last scraped</span>
							</div>
						</div>
					{/if}

					{#if analyzeError}
						<div class="inline-error">{analyzeError}</div>
					{/if}

					<button
						class="action-btn primary-action"
						onclick={handleAnalyze}
						disabled={!hasToken || !selectedGuildId}
					>
						Analyze Guild
					</button>

					<div class="idle-hint mono">
						Compares your archive with live Discord data to find new content.
					</div>
				</div>

			<!-- ─── ANALYZING: Loading ─── -->
			{:else if phase === 'analyzing'}
				<div class="phase-center">
					<div class="spinner"></div>
					<span class="mono" style="color: var(--text-secondary)">Analyzing {selectedGuild?.name ?? 'guild'}...</span>
				</div>

			<!-- ─── ANALYZED: Results + channel picker ─── -->
			{:else if phase === 'analyzed' && analyzeResult}
				<div class="phase-analyzed">
					<!-- Summary bar -->
					<div class="analyze-header">
						<span class="analyze-guild-name">{analyzeResult.guild_name}</span>
						<button class="text-btn" onclick={handleReset}>Back</button>
					</div>

					<div class="freshness-bar">
						{#if analyzeResult}
							{@const total = analyzeResult.channels.length}
							{@const upToDate = analyzeResult.summary.up_to_date ?? 0}
							{@const hasNew = analyzeResult.summary.has_new_messages ?? 0}
							{@const newCh = analyzeResult.summary.new ?? 0}
							{@const never = analyzeResult.summary.never_scraped ?? 0}
							<div class="freshness-track">
								{#if upToDate > 0}
									<div class="freshness-seg seg-uptodate" style="width: {(upToDate / total) * 100}%"></div>
								{/if}
								{#if hasNew > 0}
									<div class="freshness-seg seg-updated" style="width: {(hasNew / total) * 100}%"></div>
								{/if}
								{#if newCh > 0}
									<div class="freshness-seg seg-new" style="width: {(newCh / total) * 100}%"></div>
								{/if}
								{#if never > 0}
									<div class="freshness-seg seg-never" style="width: {(never / total) * 100}%"></div>
								{/if}
							</div>
							<div class="freshness-breakdown">
								{#if hasNew > 0}
									<details class="breakdown-group">
										<summary class="breakdown-header">
											<span class="legend-dot dot-updated"></span>
											<span class="breakdown-label">{hasNew} channel{hasNew > 1 ? 's' : ''} with new messages</span>
										</summary>
										<ul class="breakdown-list">
											{#each analyzeResult.channels.filter(c => c.status === 'has_new_messages') as ch}
												<li class="breakdown-ch"><span class="ch-icon mono">{channelIcon(ch.type)}</span>{ch.name}<span class="breakdown-meta mono">{ch.archived_message_count.toLocaleString()} archived</span></li>
											{/each}
										</ul>
									</details>
								{/if}
								{#if newCh > 0}
									<details class="breakdown-group">
										<summary class="breakdown-header">
											<span class="legend-dot dot-new"></span>
											<span class="breakdown-label">{newCh} new channel{newCh > 1 ? 's' : ''}</span>
										</summary>
										<ul class="breakdown-list">
											{#each analyzeResult.channels.filter(c => c.status === 'new') as ch}
												<li class="breakdown-ch"><span class="ch-icon mono">{channelIcon(ch.type)}</span>{ch.name}</li>
											{/each}
										</ul>
									</details>
								{/if}
								{#if never > 0}
									<details class="breakdown-group">
										<summary class="breakdown-header">
											<span class="legend-dot dot-never"></span>
											<span class="breakdown-label">{never} never scraped</span>
										</summary>
										<ul class="breakdown-list">
											{#each analyzeResult.channels.filter(c => c.status === 'never_scraped') as ch}
												<li class="breakdown-ch"><span class="ch-icon mono">{channelIcon(ch.type)}</span>{ch.name}</li>
											{/each}
										</ul>
									</details>
								{/if}
								{#if upToDate > 0}
									<details class="breakdown-group">
										<summary class="breakdown-header">
											<span class="legend-dot dot-uptodate"></span>
											<span class="breakdown-label">{upToDate} current</span>
										</summary>
										<ul class="breakdown-list">
											{#each analyzeResult.channels.filter(c => c.status === 'up_to_date') as ch}
												<li class="breakdown-ch"><span class="ch-icon mono">{channelIcon(ch.type)}</span>{ch.name}<span class="breakdown-meta mono">{ch.archived_message_count.toLocaleString()} msgs</span></li>
											{/each}
										</ul>
									</details>
								{/if}
							</div>
						{/if}
					</div>

					<!-- Channel picker -->
					{#if analyzeChannels.length > 0}
						<div class="channel-picker">
							<div class="picker-toolbar">
								<div class="picker-actions">
									<button class="text-btn" onclick={selectNeedsScrape}>Select needs scrape ({needsScrapeCount})</button>
									<span class="sep">|</span>
									<button class="text-btn" onclick={selectAllVisible}>All</button>
									<span class="sep">|</span>
									<button class="text-btn" onclick={deselectAllVisible}>None</button>
								</div>
								{#if analyzeChannels.length > 15}
									<input
										class="filter-input"
										type="text"
										placeholder="Filter..."
										bind:value={channelFilter}
									/>
								{/if}
							</div>

							<div class="channel-list">
								{#each [...groupedChannels.entries()] as [category, channels]}
									<div class="cat-group">
										<button class="cat-header" onclick={() => toggleCategory(category)}>
											<span class="cat-arrow" class:collapsed={collapsedCategories.has(category)}>&#x25BE;</span>
											{category}
										</button>
										{#if !collapsedCategories.has(category)}
											{#each channels as ch}
												<label class="ch-row" class:selected={selectedChannelIds.has(ch.id)}>
													<input
														type="checkbox"
														checked={selectedChannelIds.has(ch.id)}
														onchange={() => toggleChannel(ch.id)}
													/>
													<span class="ch-icon mono">{channelIcon(ch.type)}</span>
													<span class="ch-name">{ch.name}</span>
													{#if ch.status !== 'up_to_date'}
														<span class="ch-status ch-status-{ch.status}">
															{#if ch.status === 'new'}new
															{:else if ch.status === 'has_new_messages'}updated
															{:else if ch.status === 'never_scraped'}empty{/if}
														</span>
													{/if}
													<span class="ch-count mono">{ch.archived_message_count.toLocaleString()}</span>
												</label>
											{/each}
										{/if}
									</div>
								{/each}
							</div>

							<div class="picker-footer mono">
								{selectedCount} channel{selectedCount !== 1 ? 's' : ''} selected
							</div>
						</div>
					{/if}

					{#if actionError}
						<div class="inline-error">{actionError}</div>
					{/if}

					<div class="action-row">
						<button
							class="action-btn primary-action"
							onclick={handleStart}
							disabled={!hasToken || selectedCount === 0}
						>
							{#if selectedCount > 0}
								Scrape {selectedCount} Channel{selectedCount > 1 ? 's' : ''}
							{:else}
								Select Channels to Scrape
							{/if}
						</button>
						<button
							class="action-btn secondary-action"
							onclick={handleStart}
							disabled={!hasToken}
						>
							Full Guild
						</button>
					</div>
				</div>

			<!-- ─── SCRAPING: Live progress ─── -->
			{:else if (phase === 'scraping') && currentJob}
				<div class="phase-scraping">
					<div class="scrape-header">
						<span class="scrape-status-badge" style="color: {statusColor(currentJob.status)}">
							{currentJob.status}
						</span>
						<span class="mono" style="color: var(--text-muted); font-size: 12px">{currentJob.id}</span>
					</div>

					<div class="scrape-counters">
						<div class="counter">
							<span class="counter-val">{currentJob.progress.channels_done}{#if currentJob.progress.channels_total > 0}<span class="counter-total"> / {currentJob.progress.channels_total}</span>{/if}</span>
							<span class="counter-lbl">channels</span>
						</div>
						<div class="counter">
							<span class="counter-val">{currentJob.progress.messages_scraped.toLocaleString()}</span>
							<span class="counter-lbl">messages</span>
						</div>
						<div class="counter">
							<span class="counter-val">{currentJob.progress.attachments_found.toLocaleString()}</span>
							<span class="counter-lbl">attachments</span>
						</div>
						<div class="counter">
							<span class="counter-val">{formatDuration(currentJob.duration_seconds)}</span>
							<span class="counter-lbl">elapsed</span>
						</div>
					</div>

					{#if currentJob.progress.current_channel}
						<div class="current-channel mono">
							Scraping #{currentJob.progress.current_channel}
						</div>
					{/if}

					{#if currentJob.progress.channels_total > 0}
						{@const pct = Math.round((currentJob.progress.channels_done / currentJob.progress.channels_total) * 100)}
						<div class="progress-track">
							<div class="progress-fill" style="width: {pct}%"></div>
						</div>
					{:else}
						<div class="pulse-bar">
							<div class="pulse-fill"></div>
						</div>
					{/if}

					{#if currentJob.progress.errors.length > 0}
						<details class="scrape-warnings">
							<summary class="mono">{currentJob.progress.errors.length} warning(s)</summary>
							<ul>
								{#each currentJob.progress.errors as err}
									<li class="mono">{err}</li>
								{/each}
							</ul>
						</details>
					{/if}

					{#if currentJob.error_message}
						<div class="inline-error">{currentJob.error_message}</div>
					{/if}

					<button class="action-btn cancel-action" onclick={handleCancel}>
						Cancel
					</button>
				</div>

			<!-- ─── COMPLETED / FAILED ─── -->
			{:else if (phase === 'completed' || phase === 'failed') && currentJob}
				<div class="phase-done">
					<div class="done-status" style="color: {statusColor(currentJob.status)}">
						{currentJob.status === 'completed' ? 'Scrape Complete' : 'Scrape Failed'}
					</div>

					<div class="scrape-counters">
						<div class="counter">
							<span class="counter-val">{currentJob.progress.channels_done}{#if currentJob.progress.channels_total > 0}<span class="counter-total"> / {currentJob.progress.channels_total}</span>{/if}</span>
							<span class="counter-lbl">channels</span>
						</div>
						<div class="counter">
							<span class="counter-val">{currentJob.progress.messages_scraped.toLocaleString()}</span>
							<span class="counter-lbl">messages</span>
						</div>
						<div class="counter">
							<span class="counter-val">{currentJob.progress.attachments_found.toLocaleString()}</span>
							<span class="counter-lbl">attachments</span>
						</div>
						<div class="counter">
							<span class="counter-val">{formatDuration(currentJob.duration_seconds)}</span>
							<span class="counter-lbl">duration</span>
						</div>
					</div>

					{#if currentJob.error_message}
						<div class="inline-error">{currentJob.error_message}</div>
					{/if}

					<button class="action-btn primary-action" onclick={handleReset}>
						Analyze Again
					</button>
				</div>
			{/if}
		</div>

		<!-- Utilities drawer -->
		<div class="utilities" class:open={utilitiesOpen}>
			<button class="utilities-toggle" onclick={() => utilitiesOpen = !utilitiesOpen}>
				<span class="toggle-arrow" class:open={utilitiesOpen}>&#x25BE;</span>
				<span>Utilities</span>
				<span class="toggle-hint mono">
					{#if dlStats}Downloads{/if}
					{#if showTransfer}&ensp;Transfer{/if}
					&ensp;History
				</span>
			</button>

			{#if utilitiesOpen}
				<div class="utilities-content fade-in">

					<!-- Downloads -->
					<div class="util-section">
						<h3 class="util-title">Image Downloads</h3>
						{#if dlStats}
							{#if dlStats.attachments_dir}
								<div class="dl-path mono">{dlStats.attachments_dir}</div>
							{/if}
							<div class="dl-row">
								<span class="mono">{dlStats.downloaded.toLocaleString()} / {dlStats.total_images.toLocaleString()}</span>
								<span class="mono">{formatBytes(dlStats.downloaded_bytes)}</span>
								<span class="mono">{dlPercent(dlStats)}%</span>
							</div>
							<div class="progress-track">
								<div class="progress-fill" style="width: {dlPercent(dlStats)}%"></div>
							</div>
							<div class="dl-tags">
								{#if dlStats.pending > 0}
									<span class="dl-tag tag-pending">{dlStats.pending.toLocaleString()} pending</span>
								{/if}
								{#if dlStats.failed > 0}
									<span class="dl-tag tag-failed">{dlStats.failed.toLocaleString()} failed</span>
								{/if}
							</div>
						{/if}

						{#if isDownloading && downloadJob}
							<div class="dl-progress-live">
								<div class="dl-row">
									<span class="mono" style="color: var(--accent)">{downloadJob.status}</span>
									{#if downloadJob.current_channel}
										<span class="mono">{downloadJob.current_channel}</span>
									{/if}
								</div>
								<div class="dl-row">
									<span class="mono">{downloadJob.downloaded} downloaded</span>
									{#if downloadJob.failed > 0}
										<span class="mono" style="color: var(--error)">{downloadJob.failed} failed</span>
									{/if}
									{#if downloadJob.skipped > 0}
										<span class="mono">{downloadJob.skipped} skipped</span>
									{/if}
								</div>
								{#if downloadJob.total_images > 0}
									{@const pct = Math.round(((downloadJob.downloaded + downloadJob.failed + downloadJob.skipped) / downloadJob.total_images) * 100)}
									<div class="progress-track">
										<div class="progress-fill" style="width: {pct}%"></div>
									</div>
								{:else}
									<div class="pulse-bar"><div class="pulse-fill"></div></div>
								{/if}
								<button class="action-btn" style="margin-top: var(--sp-2)" onclick={handleCancelDownload}>
									Cancel Download
								</button>
							</div>
						{:else}
							{#if downloadError}
								<div class="inline-error">{downloadError}</div>
							{/if}
							{#if downloadJob && downloadJob.status === 'completed'}
								<div class="dl-done mono" style="color: var(--success); font-size: 12px; margin-top: var(--sp-2)">
									Last download: {downloadJob.downloaded} images
								</div>
							{/if}
							{#if dlStats && dlStats.pending > 0}
								<button class="action-btn primary-action" style="margin-top: var(--sp-3)" onclick={handleStartDownload}>
									Download {dlStats.pending.toLocaleString()} Images
								</button>
							{/if}
						{/if}
					</div>

					<!-- Transfer -->
					{#if showTransfer}
						<div class="util-section">
							<h3 class="util-title">Data Transfer</h3>
							<div class="transfer-row">
								<span>SQLite</span>
								<span class="transfer-arrow">&#x2192;</span>
								<span>PostgreSQL</span>
							</div>

							{#if transferStatus && transferStatus.status !== 'idle'}
								<div class="transfer-progress">
									<div class="dl-row">
										<span class="mono" style="color: {statusColor(transferStatus.status)}">
											{transferStatus.status}
										</span>
										<span class="mono">{transferStatus.rows_transferred.toLocaleString()} / {transferStatus.total_rows.toLocaleString()} rows</span>
										<span class="mono">{transferPercent}%</span>
									</div>
									<div class="progress-track">
										<div class="progress-fill" style="width: {transferPercent}%"></div>
									</div>
									{#if transferStatus.error}
										<div class="inline-error">{transferStatus.error}</div>
									{/if}
								</div>
							{/if}

							{#if transferError}
								<div class="inline-error">{transferError}</div>
							{/if}

							<div class="util-actions">
								{#if transferBusy}
									<button class="action-btn cancel-action" onclick={handleCancelTransfer}>Cancel</button>
								{:else}
									<button class="action-btn secondary-action" onclick={handleStartTransfer}>Transfer Data</button>
								{/if}
							</div>
						</div>
					{/if}

					<!-- History -->
					<div class="util-section">
						<h3 class="util-title">Scrape History</h3>
						{#if history.length === 0}
							<p class="mono" style="color: var(--text-muted); font-size: 13px">No completed jobs yet.</p>
						{:else}
							<div class="history-table-wrap">
								<table class="history-table">
									<thead>
										<tr>
											<th>Status</th>
											<th>Scope</th>
											<th>Messages</th>
											<th>Duration</th>
											<th>When</th>
										</tr>
									</thead>
									<tbody>
										{#each history as job}
											{@const hasError = job.status === 'failed' || job.progress.errors.length > 0}
											<tr class:has-detail={hasError}>
												<td>
													<span style="color: {statusColor(job.status)}" class="mono">{job.status}</span>
												</td>
												<td>
													{#if job.scope === 'channels' && job.channel_ids}
														{job.channel_ids.length} ch
													{:else}
														full
													{/if}
												</td>
												<td class="mono">{job.progress.messages_scraped.toLocaleString()}</td>
												<td class="mono">{formatDuration(job.duration_seconds)}</td>
												<td class="mono">{formatDate(job.started_at)}</td>
											</tr>
											{#if hasError}
												<tr class="detail-row">
													<td colspan="5">
														{#if job.error_message}
															<div class="history-error">{job.error_message}</div>
														{/if}
														{#if job.progress.errors.length > 0}
															<details class="history-warnings">
																<summary class="mono">{job.progress.errors.length} warning(s)</summary>
																<ul>
																	{#each job.progress.errors as err}
																		<li class="mono">{err}</li>
																	{/each}
																</ul>
															</details>
														{/if}
													</td>
												</tr>
											{/if}
										{/each}
									</tbody>
								</table>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.control {
		max-width: 680px;
		margin: 0 auto;
		padding: var(--sp-8) var(--sp-6);
	}

	/* Header */
	.page-header {
		margin-bottom: var(--sp-6);
	}

	.page-title {
		font-size: 32px;
		font-weight: 700;
		letter-spacing: -0.03em;
		line-height: 1.1;
	}

	.dot { color: var(--accent); }

	/* Center states */
	.center-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-16) 0;
		color: var(--text-muted);
	}

	.spinner {
		width: 20px;
		height: 20px;
		border: 2px solid var(--border-strong);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.spinner-sm {
		width: 14px;
		height: 14px;
		border-width: 1.5px;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* Primary panel */
	.primary-panel {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		padding: var(--sp-6);
		min-height: 200px;
	}

	.panel-alert {
		font-size: 13px;
		color: var(--warning);
		padding: var(--sp-3) var(--sp-4);
		background: rgba(251, 191, 36, 0.06);
		border: 1px solid rgba(251, 191, 36, 0.12);
		border-radius: var(--radius-md);
		margin-bottom: var(--sp-5);
	}

	.panel-alert code {
		font-family: var(--font-mono);
		font-size: 12px;
		padding: 1px 4px;
		background: var(--bg-overlay);
		border-radius: var(--radius-sm);
	}

	/* ─── Idle phase ─── */
	.phase-idle {
		display: flex;
		flex-direction: column;
		gap: var(--sp-5);
	}

	.guild-row {
		display: flex;
		flex-direction: column;
		gap: var(--sp-1);
	}

	.label {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.guild-select {
		width: 100%;
		padding: var(--sp-2) var(--sp-3);
		font-family: var(--font-mono);
		font-size: 14px;
		background: var(--bg-raised);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		color: var(--text-primary);
		transition: border-color 0.15s var(--ease-out);
	}

	.guild-select:focus {
		outline: none;
		border-color: var(--accent-dim);
	}

	.guild-select:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.guild-select option {
		background: var(--bg-raised);
		color: var(--text-primary);
	}

	.health-strip {
		display: flex;
		justify-content: space-between;
		padding: var(--sp-4);
		background: var(--bg-raised);
		border-radius: var(--radius-md);
	}

	.health-stat {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1px;
		flex: 1;
	}

	.health-val {
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.health-lbl {
		font-size: 11px;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.idle-hint {
		font-size: 12px;
		color: var(--text-muted);
		text-align: center;
	}

	/* ─── Analyzing ─── */
	.phase-center {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-12) 0;
	}

	/* ─── Analyzed phase ─── */
	.phase-analyzed {
		display: flex;
		flex-direction: column;
		gap: var(--sp-4);
	}

	.analyze-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.analyze-guild-name {
		font-weight: 600;
		font-size: 15px;
	}

	/* Freshness bar — the signature element */
	.freshness-bar {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	.freshness-track {
		display: flex;
		height: 6px;
		border-radius: 3px;
		overflow: hidden;
		background: var(--bg-raised);
	}

	.freshness-seg {
		height: 100%;
		transition: width 0.4s var(--ease-out);
	}

	.seg-uptodate { background: #4ade80; }
	.seg-updated { background: var(--warning); }
	.seg-new { background: #60a5fa; }
	.seg-never { background: var(--error); opacity: 0.7; }

	.freshness-breakdown {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.breakdown-group {
		font-size: 13px;
	}

	.breakdown-header {
		display: flex;
		align-items: center;
		gap: 6px;
		cursor: pointer;
		padding: var(--sp-1) 0;
		color: var(--text-secondary);
		list-style: none;
	}

	.breakdown-header::-webkit-details-marker {
		display: none;
	}

	.breakdown-header::before {
		content: '▸';
		font-size: 10px;
		color: var(--text-muted);
		transition: transform 0.15s var(--ease-out);
		display: inline-block;
	}

	details[open] > .breakdown-header::before {
		transform: rotate(90deg);
	}

	.breakdown-label {
		font-size: 12px;
	}

	.breakdown-list {
		list-style: none;
		padding: 0 0 var(--sp-1) var(--sp-5);
		margin: 0;
		max-height: 140px;
		overflow-y: auto;
	}

	.breakdown-ch {
		display: flex;
		align-items: center;
		gap: var(--sp-1);
		font-size: 12px;
		color: var(--text-secondary);
		padding: 1px 0;
	}

	.breakdown-meta {
		margin-left: auto;
		font-size: 11px;
		color: var(--text-muted);
	}

	.legend-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.dot-uptodate { background: #4ade80; }
	.dot-updated { background: var(--warning); }
	.dot-new { background: #60a5fa; }
	.dot-never { background: var(--error); opacity: 0.7; }

	/* Channel picker */
	.channels-loading {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--sp-2);
		padding: var(--sp-6);
		color: var(--text-muted);
		font-size: 13px;
	}

	.channel-picker {
		display: flex;
		flex-direction: column;
	}

	.picker-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--sp-2) var(--sp-3);
		background: var(--bg-raised);
		border: 1px solid var(--border);
		border-radius: var(--radius-md) var(--radius-md) 0 0;
		border-bottom: none;
	}

	.picker-actions {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.text-btn {
		background: none;
		border: none;
		color: var(--accent-text);
		cursor: pointer;
		font-size: 12px;
		padding: 0;
		transition: color 0.15s var(--ease-out);
	}

	.text-btn:hover { color: var(--accent); }

	.sep {
		color: var(--text-faint);
		font-size: 12px;
	}

	.filter-input {
		padding: 2px var(--sp-2);
		font-family: var(--font-mono);
		font-size: 12px;
		background: var(--bg-overlay);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		width: 100px;
	}

	.filter-input:focus {
		outline: none;
		border-color: var(--accent-dim);
	}

	.channel-list {
		max-height: 320px;
		overflow-y: auto;
		background: var(--bg-raised);
		border: 1px solid var(--border);
		border-radius: 0 0 var(--radius-md) var(--radius-md);
	}

	.cat-group {
		border-bottom: 1px solid var(--border);
	}

	.cat-group:last-child {
		border-bottom: none;
	}

	.cat-header {
		display: flex;
		align-items: center;
		gap: var(--sp-1);
		width: 100%;
		padding: var(--sp-2) var(--sp-3);
		background: none;
		border: none;
		cursor: pointer;
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		transition: color 0.15s var(--ease-out);
	}

	.cat-header:hover { color: var(--text-secondary); }

	.cat-arrow {
		font-size: 10px;
		transition: transform 0.15s var(--ease-out);
		display: inline-block;
	}

	.cat-arrow.collapsed {
		transform: rotate(-90deg);
	}

	.ch-row {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-1) var(--sp-3);
		padding-left: var(--sp-5);
		cursor: pointer;
		transition: background 0.1s var(--ease-out);
		font-size: 13px;
	}

	.ch-row:hover { background: var(--bg-hover); }

	.ch-row.selected {
		background: rgba(232, 168, 56, 0.04);
	}

	.ch-row input[type="checkbox"] {
		accent-color: var(--accent);
		width: 13px;
		height: 13px;
		flex-shrink: 0;
	}

	.ch-icon {
		flex-shrink: 0;
		width: 14px;
		text-align: center;
		font-size: 13px;
		color: var(--text-muted);
	}

	.ch-name {
		flex: 1;
		color: var(--text-primary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.ch-status {
		font-size: 10px;
		font-weight: 600;
		padding: 1px 5px;
		border-radius: 3px;
		text-transform: uppercase;
		letter-spacing: 0.02em;
		flex-shrink: 0;
	}

	.ch-status-new {
		background: rgba(96, 165, 250, 0.12);
		color: #60a5fa;
	}

	.ch-status-has_new_messages {
		background: rgba(251, 191, 36, 0.12);
		color: var(--warning);
	}

	.ch-status-never_scraped {
		background: rgba(248, 113, 113, 0.1);
		color: var(--error);
	}

	.ch-count {
		color: var(--text-muted);
		font-size: 11px;
		flex-shrink: 0;
	}

	.picker-footer {
		padding: var(--sp-2) 0;
		font-size: 12px;
		color: var(--text-secondary);
		text-align: center;
	}

	/* ─── Scraping phase ─── */
	.phase-scraping {
		display: flex;
		flex-direction: column;
		gap: var(--sp-4);
	}

	.scrape-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.scrape-status-badge {
		font-family: var(--font-mono);
		font-size: 13px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.scrape-counters {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--sp-3);
		padding: var(--sp-4);
		background: var(--bg-raised);
		border-radius: var(--radius-md);
	}

	.counter {
		text-align: center;
	}

	.counter-val {
		display: block;
		font-family: var(--font-mono);
		font-size: 20px;
		font-weight: 700;
		color: var(--accent-text);
		line-height: 1.2;
	}

	.counter-total {
		font-size: 14px;
		font-weight: 400;
		color: var(--text-muted);
	}

	.counter-lbl {
		font-size: 10px;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.current-channel {
		font-size: 13px;
		color: var(--text-secondary);
		text-align: center;
	}

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

	.scrape-warnings {
		font-size: 12px;
	}

	.scrape-warnings summary {
		cursor: pointer;
		color: var(--warning);
		padding: var(--sp-1) 0;
	}

	.scrape-warnings ul {
		list-style: none;
		padding: var(--sp-2) var(--sp-3);
		max-height: 150px;
		overflow-y: auto;
	}

	.scrape-warnings li {
		padding: var(--sp-1) 0;
		color: var(--text-secondary);
		border-bottom: 1px solid var(--border);
		font-size: 11px;
	}

	/* ─── Done phase ─── */
	.phase-done {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-5);
		padding: var(--sp-4) 0;
	}

	.done-status {
		font-size: 18px;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	/* ─── Buttons ─── */
	.action-btn {
		padding: var(--sp-2) var(--sp-5);
		font-size: 14px;
		font-weight: 600;
		border-radius: var(--radius-md);
		transition: all 0.15s var(--ease-out);
		cursor: pointer;
		border: none;
	}

	.action-btn:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}

	.primary-action {
		width: 100%;
		background: var(--accent);
		color: var(--bg-base);
	}

	.primary-action:hover:not(:disabled) {
		background: var(--accent-dim);
	}

	.secondary-action {
		background: var(--bg-raised);
		color: var(--text-secondary);
		border: 1px solid var(--border);
	}

	.secondary-action:hover:not(:disabled) {
		color: var(--text-primary);
		border-color: var(--border-strong);
	}

	.cancel-action {
		width: 100%;
		background: rgba(248, 113, 113, 0.12);
		color: var(--error);
		border: 1px solid rgba(248, 113, 113, 0.2);
	}

	.cancel-action:hover {
		background: rgba(248, 113, 113, 0.2);
	}

	.action-row {
		display: flex;
		gap: var(--sp-3);
	}

	.action-row .primary-action {
		flex: 1;
	}

	.inline-error {
		font-size: 13px;
		color: var(--error);
		padding: var(--sp-2) var(--sp-3);
		background: rgba(248, 113, 113, 0.06);
		border-radius: var(--radius-sm);
	}

	/* ─── Utilities drawer ─── */
	.utilities {
		margin-top: var(--sp-6);
	}

	.utilities-toggle {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		width: 100%;
		padding: var(--sp-3) 0;
		font-size: 13px;
		font-weight: 600;
		color: var(--text-secondary);
		cursor: pointer;
		transition: color 0.15s var(--ease-out);
		background: none;
		border: none;
		border-top: 1px solid var(--border);
	}

	.utilities-toggle:hover {
		color: var(--text-primary);
	}

	.toggle-arrow {
		font-size: 11px;
		transition: transform 0.15s var(--ease-out);
		display: inline-block;
	}

	.toggle-arrow.open {
		transform: rotate(0deg);
	}

	.toggle-arrow:not(.open) {
		transform: rotate(-90deg);
	}

	.toggle-hint {
		margin-left: auto;
		font-size: 11px;
		color: var(--text-muted);
		font-weight: 400;
	}

	.utilities-content {
		display: flex;
		flex-direction: column;
		gap: var(--sp-5);
		padding: var(--sp-4) 0;
	}

	.util-section {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
		padding: var(--sp-4);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
	}

	.util-title {
		font-size: 13px;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.util-actions {
		display: flex;
		justify-content: flex-end;
	}

	/* Downloads */
	.dl-path {
		font-size: 11px;
		color: var(--text-muted);
		padding: var(--sp-1) var(--sp-2);
		background: var(--bg-raised);
		border-radius: var(--radius-sm);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.dl-row {
		display: flex;
		justify-content: space-between;
		font-size: 12px;
		color: var(--text-secondary);
	}

	.progress-track {
		height: 4px;
		background: var(--bg-raised);
		border-radius: 2px;
		overflow: hidden;
	}

	.progress-fill {
		height: 100%;
		background: var(--accent);
		border-radius: 2px;
		transition: width 0.4s var(--ease-out);
		min-width: 2px;
	}

	.dl-progress-live {
		margin-top: var(--sp-3);
		padding: var(--sp-3);
		background: rgba(var(--accent-rgb, 99, 102, 241), 0.06);
		border-radius: var(--radius-sm);
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	.dl-tags {
		display: flex;
		gap: var(--sp-2);
	}

	.dl-tag {
		font-size: 11px;
		padding: 1px 6px;
		border-radius: var(--radius-sm);
		font-weight: 500;
	}

	.tag-pending {
		background: rgba(251, 191, 36, 0.1);
		color: var(--warning);
	}

	.tag-failed {
		background: rgba(248, 113, 113, 0.1);
		color: var(--error);
	}

	/* Transfer */
	.transfer-row {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--sp-3);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.transfer-arrow {
		color: var(--accent);
		font-weight: 700;
	}

	.transfer-progress {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	/* History */
	.history-table-wrap {
		overflow-x: auto;
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		background: var(--bg-raised);
	}

	.history-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 12px;
	}

	.history-table th {
		text-align: left;
		padding: var(--sp-2) var(--sp-3);
		font-size: 10px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		border-bottom: 1px solid var(--border);
		white-space: nowrap;
	}

	.history-table td {
		padding: var(--sp-2) var(--sp-3);
		border-bottom: 1px solid var(--border);
		white-space: nowrap;
		color: var(--text-secondary);
	}

	.history-table tr:last-child td {
		border-bottom: none;
	}

	.history-table tr:hover td {
		background: var(--bg-hover);
	}

	.detail-row td {
		padding: 0 var(--sp-3) var(--sp-2) !important;
		border-bottom: 1px solid var(--border);
	}

	.detail-row:hover td {
		background: transparent !important;
	}

	.history-error {
		font-size: 11px;
		font-family: var(--font-mono);
		color: var(--error);
		padding: var(--sp-1) var(--sp-2);
		background: rgba(248, 113, 113, 0.06);
		border-radius: var(--radius-sm);
		margin-bottom: var(--sp-1);
	}

	.history-warnings {
		font-size: 11px;
	}

	.history-warnings summary {
		cursor: pointer;
		color: var(--warning);
		font-size: 11px;
		padding: var(--sp-1) 0;
	}

	.history-warnings ul {
		list-style: none;
		padding: var(--sp-1) var(--sp-3);
		margin: 0;
	}

	.history-warnings li {
		padding: 1px 0;
		color: var(--text-secondary);
		font-size: 10px;
	}
</style>
