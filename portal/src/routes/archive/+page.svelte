<script lang="ts">
	// The Archive screen: scrape control. Run a scrape of a guild, watch the scrape job,
	// see the local attachments in the attachments dir, and the jobs that ended.
	//
	// Scrape status is the shell's (#lib/scrape-status.svelte.ts): read once, and polled
	// by the sidebar's archive card only while a job runs, for this screen too. This
	// screen reads it again only after it starts or cancels a job, and reads history
	// (and download stats) again only when a job ends.
	import { onMount } from 'svelte';
	import {
		ApiError,
		cancelScrape,
		getApiToken,
		getDownloadStats,
		getScrapeHistory,
		setApiToken,
		startScrape
	} from '#lib/api.ts';
	import AttachmentsCard from '#lib/components/archive/AttachmentsCard.svelte';
	import ScrapeHistory from '#lib/components/archive/ScrapeHistory.svelte';
	import ScrapeJobCard from '#lib/components/archive/ScrapeJobCard.svelte';
	import Alert from '#lib/components/ui/Alert.svelte';
	import Badge from '#lib/components/ui/Badge.svelte';
	import Button from '#lib/components/ui/Button.svelte';
	import Icon from '#lib/components/ui/Icon.svelte';
	import Skeleton from '#lib/components/ui/Skeleton.svelte';
	import { scrapeStatus } from '#lib/scrape-status.svelte.ts';
	import { shell } from '#lib/shell.svelte.ts';
	import type { DownloadStatsResponse, ScrapeJob } from '#lib/types.ts';

	/** The guild select's value for a guild the archive does not hold yet. */
	const OTHER = 'other';

	const guilds = shell.guilds;
	const status = $derived(scrapeStatus.status);
	const job = $derived(status?.current_job ?? null);
	const busy = $derived(status?.busy ?? false);
	const hasToken = $derived(status?.has_token ?? false);
	const controlEnabled = $derived(status?.control_enabled ?? false);
	/** Whether this portal can start jobs: a bot token to scrape with, an API token to ask with. */
	const canRun = $derived(hasToken && controlEnabled);

	let loading = $state(true);
	let statusError = $state('');
	let history: ScrapeJob[] = $state([]);
	let historyError = $state('');
	let downloads: DownloadStatsResponse | null = $state(null);
	let downloadsError = $state('');

	let guildChoice = $state('');
	let otherGuildId = $state('');
	let apiToken = $state('');
	let starting = $state(false);
	let startError = $state('');

	const guildId = $derived(guildChoice === OTHER ? otherGuildId.trim() : guildChoice);
	const guildIdValid = $derived(/^\d{15,22}$/.test(guildId));

	onMount(async () => {
		guildChoice = shell.guild?.id ?? OTHER;
		apiToken = getApiToken();
		await Promise.all([loadStatus(), loadHistory(), loadDownloads()]);
		loading = false;
	});

	// When a running job ends, however its end was noticed, read what it changed once.
	let wasBusy = false;
	$effect(() => {
		const now = busy;
		if (wasBusy && !now) void Promise.all([loadHistory(), loadDownloads()]);
		wasBusy = now;
	});

	async function loadStatus() {
		await scrapeStatus.load();
		statusError = scrapeStatus.status ? '' : scrapeStatus.error;
	}

	async function loadHistory() {
		try {
			history = (await getScrapeHistory()).jobs;
			historyError = '';
		} catch (e) {
			historyError = e instanceof Error ? e.message : 'Failed to read the history';
		}
	}

	async function loadDownloads() {
		try {
			downloads = await getDownloadStats();
			downloadsError = '';
		} catch (e) {
			downloadsError = e instanceof Error ? e.message : 'Failed to read download stats';
		}
	}

	function rememberToken() {
		setApiToken(apiToken.trim());
	}

	function describeError(e: unknown, fallback: string): string {
		if (e instanceof ApiError && e.status === 401) {
			return "The API token was not accepted. Enter the server's API_AUTH_TOKEN.";
		}
		if (e instanceof ApiError && e.status === 403) {
			return 'Scrape control is turned off on the server. Set API_AUTH_TOKEN there and restart it.';
		}
		return e instanceof Error ? e.message : fallback;
	}

	async function start(event: SubmitEvent) {
		event.preventDefault();
		startError = '';
		if (!guildIdValid) {
			startError = 'Enter a guild ID: the number Discord shows with Copy Server ID.';
			return;
		}
		starting = true;
		try {
			await startScrape(guildId);
			// A job that already ended never reads as running, so what it changed is read here.
			const now = await scrapeStatus.refresh();
			if (now && !now.busy) await Promise.all([loadHistory(), loadDownloads()]);
		} catch (e) {
			startError = describeError(e, 'The scrape job could not be started');
		} finally {
			starting = false;
		}
	}

	async function cancel() {
		try {
			await cancelScrape();
		} catch (e) {
			throw new Error(describeError(e, 'The scrape job could not be cancelled'));
		}
		await scrapeStatus.refresh();
	}
</script>

<div class="archive-screen">
	<header class="page-header">
		<div>
			<h1 class="page-title">Archive</h1>
			<p class="page-sub">Scrape guilds into the archive, follow the running scrape job, and see what is on disk.</p>
		</div>
		{#if status}
			<div class="health" aria-label="Scrape control">
				<Badge tone={hasToken ? 'success' : 'neutral'} icon={hasToken ? 'circle-check' : 'circle'}>
					{hasToken ? 'Bot token set' : 'No bot token'}
				</Badge>
				<Badge tone={canRun ? 'success' : 'neutral'} icon={canRun ? 'circle-check' : 'circle'}>
					{canRun ? 'Scrape control on' : 'Read-only'}
				</Badge>
			</div>
		{/if}
	</header>

	{#if loading}
		<div class="grid" aria-busy="true">
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
	{:else}
		{#if statusError}
			<div class="alerts">
				<Alert tone="danger" title="Scrape status could not be read">{statusError}</Alert>
			</div>
		{:else if !hasToken}
			<div class="alerts">
				<Alert tone="info" title="Scrape control is read-only">
					No bot token was configured when the server started, so it cannot run scrape jobs.
					To scrape from here, set <code>DISCORD_BOT_TOKEN</code> in the server's <code>.env</code>
					{#if !controlEnabled}and an <code>API_AUTH_TOKEN</code> for this portal to ask with,{/if}
					then restart the server. The archive, its attachments and history below stay readable.
				</Alert>
			</div>
		{:else if !controlEnabled}
			<div class="alerts">
				<Alert tone="warning" title="Starting and cancelling scrape jobs is turned off">
					The server has a bot token but no <code>API_AUTH_TOKEN</code>. Set one in the server's
					<code>.env</code> and restart it, then enter it below.
				</Alert>
			</div>
		{/if}

		<div class="grid">
			<section class="card enter" aria-labelledby="run-title">
				<header class="card-header">
					<h2 class="card-title" id="run-title">
						<Icon name="play" />
						Run a scrape
					</h2>
				</header>
				<form class="card-body" onsubmit={start} aria-describedby={canRun ? undefined : 'run-disabled'}>
					<fieldset class="fields" disabled={!canRun || busy || starting}>
						<div class="field">
							<label class="label" for="guild-select">Guild</label>
							<select id="guild-select" class="control" bind:value={guildChoice}>
								{#each guilds as guild (guild.id)}
									<option value={guild.id}>{guild.name}</option>
								{/each}
								<option value={OTHER}>Another guild…</option>
							</select>
						</div>

						{#if guildChoice === OTHER}
							<div class="field">
								<label class="label" for="guild-id-input">Guild ID</label>
								<input
									id="guild-id-input"
									class="control mono"
									type="text"
									inputmode="numeric"
									autocomplete="off"
									spellcheck="false"
									placeholder="e.g. 165682173540696064"
									bind:value={otherGuildId}
								/>
								<p class="hint">The bot must be a member of the guild.</p>
							</div>
						{/if}

						<div class="field">
							<span class="label" id="scope-label">Scope</span>
							<p class="scope" aria-labelledby="scope-label">
								<Icon name="layers" size={14} />
								<span>
									The whole guild: text, voice, stage and forum channels, and active and archived threads.
									Re-scraping updates the archive.
								</span>
							</p>
						</div>

						<div class="field">
							<label class="label" for="api-token-input">API token</label>
							<input
								id="api-token-input"
								class="control mono"
								type="password"
								autocomplete="off"
								spellcheck="false"
								placeholder="API_AUTH_TOKEN"
								bind:value={apiToken}
								oninput={rememberToken}
							/>
							<p class="hint">The server's API_AUTH_TOKEN, kept in this tab only (sessionStorage).</p>
						</div>
					</fieldset>

					{#if startError}
						<Alert tone="danger">{startError}</Alert>
					{/if}

					<div class="actions">
						<Button type="submit" variant="primary" icon="play" loading={starting} disabled={!canRun || busy}>
							Start scrape
						</Button>
						{#if !canRun}
							<span class="hint" id="run-disabled">
								{hasToken ? 'Needs API_AUTH_TOKEN on the server.' : 'Needs a bot token on the server.'}
							</span>
						{:else if busy}
							<span class="hint">One scrape job runs at a time.</span>
						{/if}
					</div>
				</form>
			</section>

			<div class="enter" style:--i={1}>
				<ScrapeJobCard {job} {busy} canCancel={controlEnabled} oncancel={cancel} />
			</div>
		</div>

		<div class="enter" style:--i={2}>
			<AttachmentsCard stats={downloads} error={downloadsError} />
		</div>

		<div class="enter" style:--i={3}>
			<ScrapeHistory jobs={history} error={historyError} />
		</div>
	{/if}
</div>

<style>
	.archive-screen {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
		max-width: 1200px;
		margin: 0 auto;
		padding: var(--space-10) var(--space-6);
	}

	.page-header {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--space-4);
		flex-wrap: wrap;
	}

	.page-title {
		font: var(--type-display-lg);
		letter-spacing: var(--tracking-display-lg);
	}

	.page-sub {
		margin-top: var(--space-2);
		font: var(--type-body-md);
		color: var(--text-secondary);
	}

	.health {
		display: flex;
		gap: var(--space-2);
	}

	.alerts code {
		font: var(--type-mono-md);
		font-size: 12px;
	}

	.grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr);
		gap: var(--space-4);
		align-items: start;
	}

	@media (max-width: 1023px) {
		.grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}

	.card {
		min-width: 0;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
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

	.fields {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		min-width: 0;
		border: none;
	}

	.fields:disabled .control {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.label {
		display: block;
		margin-bottom: var(--space-1);
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-secondary);
	}

	.control {
		width: 100%;
		height: 36px;
		padding: 0 var(--space-3);
		font: var(--type-label-md);
		background: var(--bg-raised);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		transition: border-color var(--duration-micro) var(--ease-out-quint);
	}

	.control:hover:not(:disabled) {
		border-color: var(--border-strong);
	}

	.control:focus-visible {
		border-color: var(--accent-glow);
		outline-offset: 0;
	}

	.control::placeholder {
		color: var(--text-tertiary);
	}

	select.control option {
		background: var(--bg-raised);
		color: var(--text-primary);
	}

	.scope {
		display: flex;
		gap: var(--space-2);
		padding: var(--space-3);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		background: var(--bg-raised);
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.scope :global(.icon) {
		margin-top: 2px;
		color: var(--text-tertiary);
	}

	.hint {
		margin-top: var(--space-1);
		font: var(--type-body-sm);
		color: var(--text-tertiary);
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-3);
	}

	.actions .hint {
		margin-top: 0;
	}

	@media (max-width: 767px) {
		.archive-screen {
			padding: var(--space-6) var(--space-4);
		}
	}
</style>
