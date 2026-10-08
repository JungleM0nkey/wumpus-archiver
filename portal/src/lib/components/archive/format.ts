// How the Archive screen words and colours scrape jobs, sizes and times.
import type { IconName } from '../ui/icons.ts';
import type { Guild, ScrapeJob } from '../../types.ts';

export type Tone = 'neutral' | 'accent' | 'success' | 'danger' | 'warning';

type Status = ScrapeJob['status'];

const STATUS: Record<Status, { label: string; tone: Tone; icon: IconName }> = {
	pending: { label: 'pending', tone: 'neutral', icon: 'circle-dashed' },
	connecting: { label: 'connecting', tone: 'accent', icon: 'circle-dashed' },
	scraping: { label: 'scraping', tone: 'accent', icon: 'circle-dot' },
	completed: { label: 'completed', tone: 'success', icon: 'circle-check' },
	failed: { label: 'failed', tone: 'danger', icon: 'circle-x' },
	cancelled: { label: 'cancelled', tone: 'warning', icon: 'ban' }
};

/** A scrape job status's label, badge tone and icon. */
export function jobStatus(status: Status): { label: string; tone: Tone; icon: IconName } {
	return STATUS[status] ?? { label: status, tone: 'neutral', icon: 'circle' };
}

/** The archived guild a scrape job is for, or null: snowflakes match as strings. */
export function jobGuild(job: ScrapeJob, guilds: Guild[]): Guild | null {
	return guilds.find((g) => g.id === job.guild_id) ?? null;
}

/** A job's guild by name, or by id when the archive does not hold it yet. */
export function jobGuildName(job: ScrapeJob, guilds: Guild[]): string {
	return jobGuild(job, guilds)?.name ?? `Guild ${job.guild_id}`;
}

export function formatDuration(seconds: number | null): string {
	if (seconds === null) return '—';
	if (seconds < 60) return `${Math.round(seconds)}s`;
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	const s = Math.round(seconds % 60);
	return h > 0 ? `${h}h ${m}m` : `${m}m ${s}s`;
}

export function formatDateTime(iso: string | null): string {
	if (!iso) return '—';
	return new Date(iso).toLocaleString('en-US', {
		month: 'short',
		day: 'numeric',
		hour: 'numeric',
		minute: '2-digit'
	});
}

export function formatBytes(bytes: number): string {
	if (bytes <= 0) return '0 B';
	const units = ['B', 'KB', 'MB', 'GB', 'TB'];
	const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
	const value = bytes / Math.pow(1024, i);
	return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** `part` of `whole` as a whole percent; 0 when there is nothing. */
export function percent(part: number, whole: number): number {
	return whole > 0 ? Math.round((part / whole) * 100) : 0;
}
