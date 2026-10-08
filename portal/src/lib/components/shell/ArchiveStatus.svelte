<!--
	The sidebar footer's archive-status card: whether a scrape job is running, and the
	way to the Archive screen. It reads the shared scrape status (scrape-status.svelte.ts)
	and polls it while a job runs, for every screen at once.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { POLL_MS, scrapeStatus } from '#lib/scrape-status.svelte.ts';
	import { ARCHIVE_HREF, isArchivePath } from '#lib/routes.ts';
	import { shell, withGuild } from '#lib/shell.svelte.ts';
	import Icon from '../ui/Icon.svelte';
	import { tooltip } from '../ui/tooltip.ts';

	let { rail = false }: { rail?: boolean } = $props();

	onMount(() => {
		void scrapeStatus.load();
	});

	$effect(() => {
		if (!scrapeStatus.busy) return;
		const timer = setInterval(() => void scrapeStatus.refresh(), POLL_MS);
		return () => clearInterval(timer);
	});

	const job = $derived(scrapeStatus.status?.current_job ?? null);
	const phase = $derived(
		scrapeStatus.busy ? 'running' : scrapeStatus.status ? 'idle' : scrapeStatus.error ? 'unknown' : 'loading'
	);
	const title = $derived(
		phase === 'running'
			? 'Scraping'
			: phase === 'idle'
				? 'Archive idle'
				: phase === 'unknown'
					? 'Status unavailable'
					: 'Archive'
	);
	const detail = $derived.by(() => {
		if (phase === 'running' && job) {
			const where = job.progress.current_channel ? `#${job.progress.current_channel} · ` : '';
			return `${where}${job.progress.messages_scraped.toLocaleString()} messages`;
		}
		if (phase === 'idle') {
			const last = shell.guild?.last_scraped_at;
			return last ? `Scraped ${formatDate(last)}` : 'Never scraped';
		}
		return phase === 'unknown' ? 'Open the Archive screen' : '';
	});
	const summary = $derived(`${title}${detail ? ` · ${detail}` : ''}`);
	const here = $derived(isArchivePath(page.url.pathname));

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
	}
</script>

<a
	href={withGuild(ARCHIVE_HREF)}
	class="status-card"
	class:here
	data-state={phase}
	aria-current={here ? 'page' : undefined}
	aria-label="Archive screen: {summary}"
	use:tooltip={{ text: summary, enabled: rail }}
>
	<span class="mark">
		<Icon name="archive" size={18} />
		<span class="dot" aria-hidden="true"></span>
	</span>
	<span class="label text">
		<span class="title">{title}</span>
		{#if detail}<span class="detail mono truncate">{detail}</span>{/if}
	</span>
	<span class="label go"><Icon name="chevron-right" /></span>
</a>

<style>
	.status-card {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		height: 52px;
		padding: 0 var(--space-2) 0 5px;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-md);
		background: var(--bg-raised);
		color: var(--text-primary);
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			border-color var(--duration-micro) var(--ease-out-quint);
	}

	.status-card:hover,
	.status-card.here {
		background: var(--bg-overlay);
		border-color: var(--border-default);
		color: var(--text-primary);
	}

	.mark {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		background: var(--bg-inset);
		color: var(--text-secondary);
	}

	.dot {
		position: absolute;
		right: -2px;
		bottom: -2px;
		width: 10px;
		height: 10px;
		border: 2px solid var(--bg-raised);
		border-radius: var(--radius-full);
		background: var(--text-tertiary);
	}

	[data-state='idle'] .dot {
		background: var(--success);
	}

	[data-state='unknown'] .dot {
		background: var(--warning);
	}

	[data-state='running'] .mark {
		color: var(--accent);
	}

	[data-state='running'] .dot {
		background: var(--accent);
		animation: pulse var(--duration-shimmer) var(--ease-in-out) infinite;
	}

	.text {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.title {
		font: var(--type-label-md);
	}

	.detail {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
	}

	.go {
		display: inline-flex;
		color: var(--text-tertiary);
	}
</style>
