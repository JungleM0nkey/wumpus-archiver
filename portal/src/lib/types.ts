// API types matching backend schemas

export interface User {
	id: string;
	username: string;
	discriminator: string | null;
	global_name: string | null;
	avatar_url: string | null;
	bot: boolean;
	display_name: string | null;
}

export interface Guild {
	id: string;
	name: string;
	icon_url: string | null;
	owner_id: string | null;
	member_count: number | null;
	first_scraped_at: string | null;
	last_scraped_at: string | null;
	scrape_count: number;
	channel_count: number;
	message_count: number;
}

export interface Channel {
	id: string;
	guild_id: string;
	name: string;
	type: number;
	topic: string | null;
	position: number;
	parent_id: string | null;
	message_count: number;
	last_scraped_at: string | null;
}

export interface Attachment {
	id: string;
	message_id: string;
	filename: string;
	content_type: string | null;
	size: number;
	url: string;
	proxy_url: string | null;
	width: number | null;
	height: number | null;
}

export interface Reaction {
	id: string;
	message_id: string;
	emoji_name: string | null;
	emoji_id: string | null;
	emoji_animated: boolean;
	count: number;
}

export interface Message {
	id: string;
	channel_id: string;
	author_id: string | null;
	content: string;
	clean_content: string;
	created_at: string;
	edited_at: string | null;
	pinned: boolean;
	tts: boolean;
	mention_everyone: boolean;
	embeds: string | null;
	reference_id: string | null;
	author: User | null;
	attachments: Attachment[];
	reactions: Reaction[];
}

export interface MessageListResponse {
	messages: Message[];
	total: number;
	has_more: boolean;
	before_id: string | null;
	after_id: string | null;
}

export interface GuildDetail extends Guild {
	channels: Channel[];
}

export interface SearchResult {
	message: Message;
	channel_name: string;
	highlight: string;
}

export interface SearchResponse {
	results: SearchResult[];
	total: number;
	query: string;
}

export interface TopChannel {
	name: string;
	message_count: number;
}

export interface TopUser {
	id: string;
	username: string;
	display_name: string;
	avatar_url: string | null;
	message_count: number;
}

export interface Stats {
	guild_name: string;
	total_channels: number;
	total_messages: number;
	total_users: number;
	total_attachments: number;
	top_channels: TopChannel[];
	top_users: TopUser[];
}

// Discord channel types
export const ChannelType = {
	GUILD_TEXT: 0,
	DM: 1,
	GUILD_VOICE: 2,
	GROUP_DM: 3,
	GUILD_CATEGORY: 4,
	GUILD_ANNOUNCEMENT: 5,
	GUILD_STAGE_VOICE: 13,
	GUILD_FORUM: 15,
	PUBLIC_THREAD: 11,
	PRIVATE_THREAD: 12,
} as const;

export interface GalleryAttachment {
	id: string;
	message_id: string;
	filename: string;
	content_type: string | null;
	size: number;
	url: string;
	proxy_url: string | null;
	width: number | null;
	height: number | null;
	created_at: string;
	author_name: string | null;
	author_avatar_url: string | null;
	channel_id: string | null;
	channel_name: string | null;
}

export interface GalleryResponse {
	attachments: GalleryAttachment[];
	total: number;
	has_more: boolean;
	offset: number;
}

export interface TimelineGalleryGroup {
	period: string;
	label: string;
	count: number;
	attachments: GalleryAttachment[];
}

export interface TimelineGalleryResponse {
	groups: TimelineGalleryGroup[];
	total: number;
	has_more: boolean;
	offset: number;
}

// --- Scrape Control Panel types ---

export interface ScrapeProgress {
	current_channel: string;
	channels_done: number;
	channels_total: number;
	messages_scraped: number;
	attachments_found: number;
	errors: string[];
}

export interface ScrapeJob {
	id: string;
	guild_id: string;
	channel_ids: string[] | null;
	scope: 'guild' | 'channels';
	status: 'pending' | 'connecting' | 'scraping' | 'completed' | 'failed' | 'cancelled';
	progress: ScrapeProgress;
	started_at: string | null;
	completed_at: string | null;
	result: Record<string, unknown> | null;
	error_message: string | null;
	duration_seconds: number | null;
}

export interface ScrapeableChannel {
	id: string;
	name: string;
	type: number;
	type_name: string;
	parent_name: string | null;
	position: number;
	already_scraped: boolean;
	archived_message_count: number;
}

export interface ScrapeableChannelsResponse {
	guild_id: string;
	guild_name: string;
	channels: ScrapeableChannel[];
	total: number;
}

export interface AnalyzeChannel {
	id: string;
	name: string;
	type: number;
	type_name: string;
	parent_name: string | null;
	position: number;
	status: 'new' | 'has_new_messages' | 'up_to_date' | 'never_scraped';
	archived_message_count: number;
	last_scraped_at: string | null;
}

export interface AnalyzeResponse {
	guild_id: string;
	guild_name: string;
	channels: AnalyzeChannel[];
	summary: Record<string, number>;
}

export interface ScrapeStatusResponse {
	busy: boolean;
	current_job: ScrapeJob | null;
	has_token: boolean;
}

export interface ScrapeHistoryResponse {
	jobs: ScrapeJob[];
}

// --- User Profile types ---

export interface UserListItem {
	id: string;
	username: string;
	discriminator: string | null;
	global_name: string | null;
	avatar_url: string | null;
	bot: boolean;
	display_name: string | null;
	message_count: number;
	first_seen: string | null;
	last_seen: string | null;
}

export interface UserListResponse {
	users: UserListItem[];
	total: number;
	has_more: boolean;
	offset: number;
}

export interface UserChannelActivity {
	channel_id: string;
	channel_name: string;
	message_count: number;
}

export interface UserMonthlyActivity {
	period: string;
	label: string;
	count: number;
}

export interface UserProfile {
	id: string;
	username: string;
	discriminator: string | null;
	global_name: string | null;
	avatar_url: string | null;
	bot: boolean;
	display_name: string | null;
	total_messages: number;
	total_attachments: number;
	total_reactions_received: number;
	first_message_at: string | null;
	last_message_at: string | null;
	active_channels: number;
	avg_message_length: number;
	top_channels: UserChannelActivity[];
	monthly_activity: UserMonthlyActivity[];
	top_reactions_received: { emoji: string; count: number }[];
	top_words: { word: string; count: number }[];
}

// --- Download stats types ---

export interface DownloadChannelStats {
	channel_id: string;
	channel_name: string;
	downloaded: number;
	pending: number;
	failed: number;
	skipped: number;
	total_images: number;
	downloaded_bytes: number;
}

export interface DownloadStatsResponse {
	total_images: number;
	downloaded: number;
	pending: number;
	failed: number;
	skipped: number;
	downloaded_bytes: number;
	attachments_dir: string | null;
	channels: DownloadChannelStats[];
}

export interface DownloadJobStatus {
	status: 'idle' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
	total_images: number;
	downloaded: number;
	failed: number;
	skipped: number;
	current_channel: string;
	error: string | null;
	started_at: string | null;
	finished_at: string | null;
}

// --- Data source types ---

export interface DataSourceInfo {
	available?: boolean;
	label: string;
	detail: string;
}

export interface DataSourceResponse {
	active: string;
	sources: Record<string, DataSourceInfo>;
}

// --- Data transfer types ---

export interface TransferStatus {
	status: 'idle' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
	current_table: string;
	tables_done: number;
	tables_total: number;
	rows_transferred: number;
	total_rows: number;
	error: string | null;
	started_at: string | null;
	finished_at: string | null;
}
