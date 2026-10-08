// API client for wumpus-archiver backend

import type {
	Guild,
	GuildDetail,
	MessageListResponse,
	SearchResponse,
	Stats,
	TimelineGalleryResponse,
	ScrapeStatusResponse,
	ScrapeHistoryResponse,
	ScrapeJob,
	DownloadStatsResponse,
	UserListResponse,
	UserProfile,
	GuildActivity
} from './types';

const API_BASE = '/api';

/** Error thrown for non-2xx API responses; `status` is the HTTP status code. */
export class ApiError extends Error {
	status: number;

	constructor(status: number, message: string) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
	}
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${API_BASE}${path}`, init);
	if (!res.ok) {
		const body = await res.json().catch(() => ({ error: res.statusText }));
		// Our handlers return {error}; FastAPI's own errors (401/403) return {detail}
		const message = body.error || (typeof body.detail === 'string' ? body.detail : '');
		throw new ApiError(res.status, message || `API error: ${res.status} ${res.statusText}`);
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
	opts: {
		before?: string | number;
		after?: string | number;
		limit?: number;
		/** The page around this message, holding it; not with `before` or `after`. */
		around?: string | number;
	} = {}
): Promise<MessageListResponse> {
	const params = new URLSearchParams();
	if (opts.before) params.set('before', String(opts.before));
	if (opts.after) params.set('after', String(opts.after));
	if (opts.limit) params.set('limit', String(opts.limit));
	if (opts.around) params.set('around', String(opts.around));
	const qs = params.toString();
	return fetchJSON<MessageListResponse>(`/channels/${channelId}/messages${qs ? `?${qs}` : ''}`);
}

/**
 * Messages holding every term of `query`, under the filters. `query` may be empty when
 * a channel, author, `has` or date filter is given. `after` is an inclusive day and
 * `before` an exclusive one (YYYY-MM-DD, UTC); `cursor` is the last result of the
 * previous page.
 */
export async function searchMessages(
	query: string,
	opts: {
		guild_id?: string | number;
		channel_id?: string | number;
		limit?: number;
		author_id?: string | number;
		has?: 'file' | 'image' | 'video' | 'link';
		after?: string;
		before?: string;
		sort?: 'newest' | 'oldest';
		cursor?: string;
		/** Also count the matches per channel, author and month. */
		facets?: boolean;
	} = {}
): Promise<SearchResponse> {
	const params = new URLSearchParams();
	if (query) params.set('q', query);
	if (opts.guild_id) params.set('guild_id', String(opts.guild_id));
	if (opts.channel_id) params.set('channel_id', String(opts.channel_id));
	if (opts.limit) params.set('limit', String(opts.limit));
	if (opts.author_id) params.set('author_id', String(opts.author_id));
	if (opts.has) params.set('has', opts.has);
	if (opts.after) params.set('after', opts.after);
	if (opts.before) params.set('before', opts.before);
	if (opts.sort) params.set('sort', opts.sort);
	if (opts.cursor) params.set('cursor', opts.cursor);
	if (opts.facets) params.set('facets', 'true');
	return fetchJSON<SearchResponse>(`/search?${params.toString()}`);
}

/** The author's newest messages: a search with no query, scoped to the author. */
export async function getAuthorMessages(
	authorId: string | number,
	opts: { guild_id?: string | number; limit?: number } = {}
): Promise<SearchResponse> {
	const params = new URLSearchParams({ author_id: String(authorId) });
	if (opts.guild_id) params.set('guild_id', String(opts.guild_id));
	if (opts.limit) params.set('limit', String(opts.limit));
	return fetchJSON<SearchResponse>(`/search?${params.toString()}`);
}

export async function getStats(guildId: string | number): Promise<Stats> {
	return fetchJSON<Stats>(`/guilds/${guildId}/stats`);
}

export async function getGuildGalleryTimeline(
	guildId: string | number,
	opts: {
		offset?: number;
		limit?: number;
		channel_id?: string | number;
		group_by?: string;
		/** image (GIFs included), gif, video, or media for all three; the API's default is image. */
		content_type?: 'image' | 'gif' | 'video' | 'media';
		author_id?: string | number;
		order?: 'newest' | 'oldest';
	} = {}
): Promise<TimelineGalleryResponse> {
	const params = new URLSearchParams();
	if (opts.offset) params.set('offset', String(opts.offset));
	if (opts.limit) params.set('limit', String(opts.limit));
	if (opts.channel_id) params.set('channel_id', String(opts.channel_id));
	if (opts.group_by) params.set('group_by', opts.group_by);
	if (opts.content_type) params.set('content_type', opts.content_type);
	if (opts.author_id) params.set('author_id', String(opts.author_id));
	if (opts.order) params.set('order', opts.order);
	const qs = params.toString();
	return fetchJSON<TimelineGalleryResponse>(`/guilds/${guildId}/gallery/timeline${qs ? `?${qs}` : ''}`);
}

// --- Scrape control panel ---

// The API token (the server's API_AUTH_TOKEN) is kept in sessionStorage so it lasts for this
// browser tab only and is never persisted to disk.
const API_TOKEN_KEY = 'wumpus_api_token';

export function getApiToken(): string {
	try {
		return sessionStorage.getItem(API_TOKEN_KEY) ?? '';
	} catch {
		return '';
	}
}

export function setApiToken(token: string): void {
	try {
		if (token) {
			sessionStorage.setItem(API_TOKEN_KEY, token);
		} else {
			sessionStorage.removeItem(API_TOKEN_KEY);
		}
	} catch {
		// Storage unavailable (private mode, blocked): the token just won't be remembered
	}
}

function authHeaders(): Record<string, string> {
	const token = getApiToken();
	return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function getScrapeStatus(): Promise<ScrapeStatusResponse> {
	return fetchJSON<ScrapeStatusResponse>('/scrape/status');
}

/**
 * Start a scrape job for guild `guildId`, a snowflake as a string of digits. It is sent
 * as that string, which the API reads as the integer: a guild id is past the integers
 * a JS number holds exactly.
 */
export async function startScrape(guildId: string): Promise<{ job: ScrapeJob }> {
	return fetchJSON<{ job: ScrapeJob }>('/scrape/start', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', ...authHeaders() },
		body: JSON.stringify({ guild_id: guildId })
	});
}

export async function cancelScrape(): Promise<{ message: string }> {
	return fetchJSON<{ message: string }>('/scrape/cancel', {
		method: 'POST',
		headers: authHeaders()
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

// --- Guild activity ---

export async function getGuildActivity(
	guildId: string | number,
	opts: { period?: 'month' | 'week' } = {}
): Promise<GuildActivity> {
	const qs = opts.period ? `?period=${opts.period}` : '';
	return fetchJSON<GuildActivity>(`/guilds/${guildId}/activity${qs}`);
}
