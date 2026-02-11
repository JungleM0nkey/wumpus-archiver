// API client for wumpus-archiver backend

import type {
	Guild,
	GuildDetail,
	MessageListResponse,
	SearchResponse,
	Stats,
	GalleryResponse,
	TimelineGalleryResponse,
	ScrapeStatusResponse,
	ScrapeHistoryResponse,
	ScrapeJob,
	DownloadStatsResponse,
	UserListResponse,
	UserProfile
} from './types';

const API_BASE = '/api';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${API_BASE}${path}`, init);
	if (!res.ok) {
		const body = await res.json().catch(() => ({ error: res.statusText }));
		throw new Error(body.error || `API error: ${res.status} ${res.statusText}`);
	}
	return res.json();
}

export async function getGuilds(): Promise<Guild[]> {
	return fetchJSON<Guild[]>('/guilds');
}

export async function getGuild(guildId: string | number): Promise<GuildDetail> {
	return fetchJSON<GuildDetail>(`/guilds/${guildId}`);
}

export async function getMessages(
	channelId: string | number,
	opts: { before?: string | number; after?: string | number; limit?: number } = {}
): Promise<MessageListResponse> {
	const params = new URLSearchParams();
	if (opts.before) params.set('before', String(opts.before));
	if (opts.after) params.set('after', String(opts.after));
	if (opts.limit) params.set('limit', String(opts.limit));
	const qs = params.toString();
	return fetchJSON<MessageListResponse>(`/channels/${channelId}/messages${qs ? `?${qs}` : ''}`);
}

export async function searchMessages(
	query: string,
	opts: { guild_id?: string | number; channel_id?: string | number; limit?: number } = {}
): Promise<SearchResponse> {
	const params = new URLSearchParams({ q: query });
	if (opts.guild_id) params.set('guild_id', String(opts.guild_id));
	if (opts.channel_id) params.set('channel_id', String(opts.channel_id));
	if (opts.limit) params.set('limit', String(opts.limit));
	return fetchJSON<SearchResponse>(`/search?${params.toString()}`);
}

export async function getStats(guildId: string | number): Promise<Stats> {
	return fetchJSON<Stats>(`/guilds/${guildId}/stats`);
}

export async function getGallery(
	channelId: string | number,
	opts: { offset?: number; limit?: number } = {}
): Promise<GalleryResponse> {
	const params = new URLSearchParams();
	if (opts.offset) params.set('offset', String(opts.offset));
	if (opts.limit) params.set('limit', String(opts.limit));
	const qs = params.toString();
	return fetchJSON<GalleryResponse>(`/channels/${channelId}/gallery${qs ? `?${qs}` : ''}`);
}

export async function getGuildGallery(
	guildId: string | number,
	opts: { offset?: number; limit?: number; channel_id?: string | number; content_type?: string } = {}
): Promise<GalleryResponse> {
	const params = new URLSearchParams();
	if (opts.offset) params.set('offset', String(opts.offset));
	if (opts.limit) params.set('limit', String(opts.limit));
	if (opts.channel_id) params.set('channel_id', String(opts.channel_id));
	if (opts.content_type) params.set('content_type', opts.content_type);
	const qs = params.toString();
	return fetchJSON<GalleryResponse>(`/guilds/${guildId}/gallery${qs ? `?${qs}` : ''}`);
}

export async function getGuildGalleryTimeline(
	guildId: string | number,
	opts: { offset?: number; limit?: number; channel_id?: string | number; group_by?: string } = {}
): Promise<TimelineGalleryResponse> {
	const params = new URLSearchParams();
	if (opts.offset) params.set('offset', String(opts.offset));
	if (opts.limit) params.set('limit', String(opts.limit));
	if (opts.channel_id) params.set('channel_id', String(opts.channel_id));
	if (opts.group_by) params.set('group_by', opts.group_by);
	const qs = params.toString();
	return fetchJSON<TimelineGalleryResponse>(`/guilds/${guildId}/gallery/timeline${qs ? `?${qs}` : ''}`);
}

// --- Scrape control panel ---

export async function getScrapeStatus(): Promise<ScrapeStatusResponse> {
	return fetchJSON<ScrapeStatusResponse>('/scrape/status');
}

export async function startScrape(guildId: number): Promise<{ job: ScrapeJob }> {
	return fetchJSON<{ job: ScrapeJob }>('/scrape/start', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ guild_id: guildId })
	});
}

export async function cancelScrape(): Promise<{ message: string }> {
	return fetchJSON<{ message: string }>('/scrape/cancel', {
		method: 'POST'
	});
}

export async function getScrapeHistory(): Promise<ScrapeHistoryResponse> {
	return fetchJSON<ScrapeHistoryResponse>('/scrape/history');
}

// --- User profile ---

export async function getGuildUsers(
	guildId: string | number,
	opts: { offset?: number; limit?: number; sort?: string; q?: string } = {}
): Promise<UserListResponse> {
	const params = new URLSearchParams();
	if (opts.offset) params.set('offset', String(opts.offset));
	if (opts.limit) params.set('limit', String(opts.limit));
	if (opts.sort) params.set('sort', opts.sort);
	if (opts.q) params.set('q', opts.q);
	const qs = params.toString();
	return fetchJSON<UserListResponse>(`/guilds/${guildId}/users${qs ? `?${qs}` : ''}`);
}

export async function getUserProfile(
	userId: string | number,
	opts: { guild_id?: string | number } = {}
): Promise<UserProfile> {
	const params = new URLSearchParams();
	if (opts.guild_id) params.set('guild_id', String(opts.guild_id));
	const qs = params.toString();
	return fetchJSON<UserProfile>(`/users/${userId}/profile${qs ? `?${qs}` : ''}`);
}

// --- Download stats ---

export async function getDownloadStats(): Promise<DownloadStatsResponse> {
	return fetchJSON<DownloadStatsResponse>('/downloads/stats');
}
