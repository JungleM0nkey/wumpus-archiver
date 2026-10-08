<!--
	The Overview's archive health card: how many images are local attachments (from
	download stats, across the whole archive), the guild's last scrape job, and whether
	a bot token is configured. It leads to the Archive screen, where each is managed.
-->
<script lang="ts">
	import { ARCHIVE_HREF } from '#lib/routes.ts';
	import type { DownloadStatsResponse, Guild, ScrapeStatusResponse, SinceLastScrape } from '#lib/types.ts';
	import Icon from './ui/Icon.svelte';
	import type { IconName } from './ui/icons.ts';

	let {
		guild,
		downloads,
		downloadsError = '',
		status,
		sinceLastScrape
	}: {
		guild: Guild;
		downloads: DownloadStatsResponse | null;
		downloadsError?: string;
		status: ScrapeStatusResponse | null;
		sinceLastScrape: SinceLastScrape | null;
	} = $props();

	/** The archive stores naive UTC times; read one as UTC. */
	function archiveTime(iso: string): Date {
		return new Date(/(Z|[+-]\d\d:\d\d)$/.test(iso) ? iso : `${iso}Z`);
	}

	function formatDate(iso: string): string {
		return archiveTime(iso).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	function duration(fromIso: string, toIso: string): string {
		const seconds = Math.max(0, Math.round((archiveTime(toIso).getTime() - archiveTime(fromIso).getTime()) / 1000));
		if (seconds < 60) return `${seconds}s`;
		const minutes = Math.round(seconds / 60);
		if (minutes < 60) return `${minutes} min`;
		return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
	}

	const progress = $derived(
		downloads && downloads.total_images > 0 ? downloads.downloaded / downloads.total_images : null
	);
	const percent = $derived(progress === null ? null : Math.floor(progress * 100));

	interface Row {
		icon: IconName;
		tone: 'success' | 'warning' | 'muted' | 'accent';
		value: string;
		detail: string;
	}

	const scrape = $derived.by((): Row => {
		const job = status?.busy ? status.current_job : null;
		if (job) {
			const where = job.progress.current_channel ? ` in #${job.progress.current_channel}` : '';
			return {
				icon: 'activity',
				tone: 'accent',
				value: 'Running now',
				detail: `${job.progress.messages_scraped.toLocaleString()} messages so far${where}`
			};
		}
		if (sinceLastScrape) {
			return {
				icon: 'circle-check',
				tone: 'success',
				value: `Completed ${formatDate(sinceLastScrape.completed_at)}`,
				detail: `Took ${duration(sinceLastScrape.started_at, sinceLastScrape.completed_at)}`
			};
		}
		if (guild.last_scraped_at) {
			return {
				icon: 'history',
				tone: 'muted',
				value: `Scraped ${formatDate(guild.last_scraped_at)}`,
				detail: 'No completed scrape job on record yet'
			};
		}
		return { icon: 'circle-dashed', tone: 'muted', value: 'Never scraped', detail: 'Run one from the Archive screen' };
	});

	const token = $derived.by((): Row => {
		if (!status) return { icon: 'circle-help', tone: 'muted', value: 'Unknown', detail: 'Status unavailable' };
		return status.has_token
			? {
					icon: 'circle-check',
					tone: 'success',
					value: 'Configured',
					detail: 'Scrape jobs can run from the portal'
				}
			: {
					icon: 'triangle-alert',
					tone: 'warning',
					value: 'Not configured',
					detail: 'Scrape control is read-only'
				};
	});
</script>

<section class="health" aria-labelledby="health-title">
	<header class="health-head">
		<h2 id="health-title" class="health-title">Archive health</h2>
		<a class="health-link" href={ARCHIVE_HREF}>
			Open the Archive screen <Icon name="chevron-right" size={16} />
		</a>
	</header>

	<dl class="health-grid">
		<div class="health-item attachments">
			<dt>Local attachments</dt>
			{#if downloads}
				<dd class="health-value mono">{percent === null ? '—' : `${percent}%`}</dd>
				<dd class="meter-wrap">
					<div
						class="meter"
						role="progressbar"
						aria-label="Images downloaded"
						aria-valuemin={0}
						aria-valuemax={downloads.total_images}
						aria-valuenow={downloads.downloaded}
					>
						<div class="meter-fill" style:width="{(progress ?? 0) * 100}%"></div>
					</div>
				</dd>
				<dd class="health-detail">
					{#if downloads.total_images === 0}
						No images to download
					{:else}
						<span class="mono downloaded-count"
							>{downloads.downloaded.toLocaleString()} of {downloads.total_images.toLocaleString()}</span
						>
						images downloaded, across the archive{#if downloads.failed > 0}<span class="failed"
								>· {downloads.failed.toLocaleString()} failed</span
							>{/if}
					{/if}
				</dd>
			{:else}
				<dd class="health-value">—</dd>
				<dd class="health-detail">{downloadsError || 'Loading…'}</dd>
			{/if}
		</div>

		{#each [{ label: 'Last scrape job', row: scrape, cls: 'scrape' }, { label: 'Bot token', row: token, cls: 'token' }] as item (item.cls)}
			<div class="health-item {item.cls}">
				<dt>{item.label}</dt>
				<dd class="health-status {item.row.tone}">
					<Icon name={item.row.icon} size={16} />
					<span>{item.row.value}</span>
				</dd>
				<dd class="health-detail">{item.row.detail}</dd>
			</div>
		{/each}
	</dl>
</section>

<style>
	.health {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-5);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
	}

	.health-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--space-3);
		flex-wrap: wrap;
	}

	.health-title {
		font: var(--type-heading-sm);
		color: var(--text-primary);
	}

	.health-link {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		font: var(--type-label-md);
		color: var(--text-secondary);
	}

	.health-link:hover {
		color: var(--text-primary);
	}

	.health-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: var(--space-3);
		margin: 0;
	}

	.health-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-4);
		border-radius: var(--radius-sm);
		background: var(--bg-raised);
		min-width: 0;
	}

	dt {
		font: var(--type-caption);
		letter-spacing: var(--tracking-caption);
		text-transform: uppercase;
		color: var(--text-tertiary);
	}

	dd {
		margin: 0;
	}

	.health-value {
		font: var(--type-mono-num-lg);
		font-size: 22px;
		line-height: 28px;
		color: var(--text-primary);
	}

	.meter {
		height: 6px;
		border-radius: var(--radius-full);
		background: var(--accent-muted);
		overflow: hidden;
	}

	.meter-fill {
		height: 100%;
		border-radius: var(--radius-full);
		background: var(--accent);
	}

	.health-status {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font: var(--type-label-md);
		color: var(--text-primary);
		min-height: 28px;
	}

	.health-status.success :global(.icon) {
		color: var(--success);
	}

	.health-status.warning :global(.icon) {
		color: var(--warning);
	}

	.health-status.accent :global(.icon) {
		color: var(--accent);
	}

	.health-status.muted :global(.icon) {
		color: var(--text-tertiary);
	}

	.health-detail {
		font: var(--type-body-sm);
		color: var(--text-secondary);
	}

	.failed {
		margin-left: var(--space-1);
		color: var(--danger);
	}

	@media (max-width: 900px) {
		.health-grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
