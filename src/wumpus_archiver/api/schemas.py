"""Pydantic schemas for API responses."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Discord snowflake IDs exceed JavaScript's Number.MAX_SAFE_INTEGER (2^53-1).
# Serialize them as strings so the frontend doesn't lose precision.
Snowflake = Annotated[int, PlainSerializer(lambda v: str(v), return_type=str)]
OptionalSnowflake = Annotated[
    int | None, PlainSerializer(lambda v: str(v) if v is not None else None, return_type=str | None)
]


class UserSchema(BaseModel):
    """User response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: Snowflake
    username: str
    discriminator: str | None = None
    global_name: str | None = None
    avatar_url: str | None = None
    bot: bool = False
    display_name: str | None = None


class GuildSchema(BaseModel):
    """Guild response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: Snowflake
    name: str
    icon_url: str | None = None
    owner_id: OptionalSnowflake = None
    member_count: int | None = None
    first_scraped_at: datetime | None = None
    last_scraped_at: datetime | None = None
    scrape_count: int = 0
    channel_count: int = 0
    message_count: int = 0


class ChannelSchema(BaseModel):
    """Channel response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: Snowflake
    guild_id: Snowflake
    name: str
    type: int
    topic: str | None = None
    position: int = 0
    parent_id: OptionalSnowflake = None
    message_count: int = 0
    last_scraped_at: datetime | None = None


class AttachmentSchema(BaseModel):
    """Attachment response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: Snowflake
    message_id: Snowflake
    filename: str
    content_type: str | None = None
    size: int
    url: str
    proxy_url: str | None = None
    width: int | None = None
    height: int | None = None


class ReactionSchema(BaseModel):
    """Reaction response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: Snowflake
    message_id: Snowflake
    emoji_name: str | None = None
    emoji_id: OptionalSnowflake = None
    emoji_animated: bool = False
    count: int = 1


class MessageSchema(BaseModel):
    """Message response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: Snowflake
    channel_id: Snowflake
    author_id: OptionalSnowflake = None
    content: str = ""
    clean_content: str = ""
    created_at: datetime
    edited_at: datetime | None = None
    pinned: bool = False
    tts: bool = False
    mention_everyone: bool = False
    embeds: str | None = None
    reference_id: OptionalSnowflake = None
    author: UserSchema | None = None
    attachments: list[AttachmentSchema] = []
    reactions: list[ReactionSchema] = []


class MessageListResponse(BaseModel):
    """Paginated message list response."""

    messages: list[MessageSchema]
    total: int
    has_more: bool
    before_id: OptionalSnowflake = None
    after_id: OptionalSnowflake = None
    # Whether newer messages remain: set on a page read ``around`` a message, else null.
    has_newer: bool | None = None


class ChannelListResponse(BaseModel):
    """Channel list grouped by category."""

    channels: list[ChannelSchema]
    total: int


class GuildDetailSchema(GuildSchema):
    """Guild with channels included."""

    channels: list[ChannelSchema] = []


class SearchResultSchema(BaseModel):
    """Search result item."""

    message: MessageSchema
    channel_name: str
    highlight: str = ""


class SearchResponse(BaseModel):
    """Search results response."""

    results: list[SearchResultSchema]
    total: int
    query: str | None


class SinceLastScrapeSchema(BaseModel):
    """How the guild's totals changed since its last completed scrape job started.

    Each count is the current total minus the total when that job started, so it is
    what that job added plus anything ingested after it (see ``docs/adr/0004``).
    ``authors`` is the change in ``total_users``.
    """

    started_at: datetime
    completed_at: datetime
    messages: int
    channels: int
    authors: int
    attachments: int


class StatsSchema(BaseModel):
    """Guild statistics.

    ``top_channels`` lists text channels only. ``since_last_scrape`` is ``None`` when
    no scrape job of the guild has completed (or none was recorded), never zeros.
    """

    guild_name: str
    total_channels: int
    total_messages: int
    total_users: int
    total_attachments: int
    top_channels: list[dict[str, object]]
    top_users: list[dict[str, object]]
    since_last_scrape: SinceLastScrapeSchema | None = None


class ActivityBucketSchema(BaseModel):
    """Messages in one calendar month or ISO week, starting on ``start``."""

    start: date
    messages: int


class ActivitySchema(BaseModel):
    """A guild's activity: messages per period, oldest first, only periods holding messages."""

    period: Literal["month", "week"]
    buckets: list[ActivityBucketSchema]


class GalleryAttachmentSchema(BaseModel):
    """Attachment with message context for gallery view."""

    id: Snowflake
    message_id: Snowflake
    filename: str
    content_type: str | None = None
    size: int
    url: str
    proxy_url: str | None = None
    width: int | None = None
    height: int | None = None
    created_at: datetime
    author_name: str | None = None
    author_avatar_url: str | None = None
    channel_id: Snowflake | None = None
    channel_name: str | None = None


class GalleryResponse(BaseModel):
    """Paginated gallery response."""

    attachments: list[GalleryAttachmentSchema]
    total: int
    has_more: bool
    offset: int


class TimelineGalleryGroup(BaseModel):
    """The gallery timeline's attachments from one time period on one page."""

    period: str
    label: str
    count: int
    attachments: list[GalleryAttachmentSchema]


class TimelineGalleryResponse(BaseModel):
    """The gallery timeline: one page of attachments, grouped by time period."""

    groups: list[TimelineGalleryGroup]
    total: int
    has_more: bool
    offset: int


# --- GIF API schemas ---


class GifSchema(BaseModel):
    """Deduplicated GIF with popularity metadata."""

    id: Snowflake
    content_hash: str | None = None
    filename: str
    size: int
    width: int | None = None
    height: int | None = None
    url: str
    thumbnail_url: str | None = None
    usage_count: int = 1
    last_used: datetime | None = None
    channel_id: OptionalSnowflake = None
    channel_name: str | None = None


class GifListResponse(BaseModel):
    """Paginated GIF list response."""

    gifs: list[GifSchema]
    total: int
    has_more: bool
    offset: int


# --- Scrape control panel schemas ---


class ScrapeStartRequest(BaseModel):
    """Request to start a scrape job: `guild_id` as a string of digits (or a number)."""

    guild_id: int


class ScrapeChannelProgressSchema(BaseModel):
    """One channel of a scrape job: its name, the messages written so far, and whether it is done."""

    name: str
    messages: int = 0
    done: bool = False


class ScrapeProgressSchema(BaseModel):
    """Progress data for a running scrape job."""

    current_channel: str = ""
    channels_done: int = 0
    messages_scraped: int = 0
    attachments_found: int = 0
    errors: list[str] = []
    # The channels the job has reached, in order; the last one not done is the current one
    channels: list[ScrapeChannelProgressSchema] = []


class ScrapeJobSchema(BaseModel):
    """Response schema for a scrape job."""

    id: str
    guild_id: Snowflake
    status: str
    progress: ScrapeProgressSchema
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, object] | None = None
    error_message: str | None = None
    duration_seconds: float | None = None


class ScrapeStatusResponse(BaseModel):
    """Response for scrape status endpoint."""

    busy: bool
    current_job: ScrapeJobSchema | None = None
    has_token: bool = False
    # True when API_AUTH_TOKEN is set, i.e. start/cancel can be used with that bearer token
    control_enabled: bool = False


class ScrapeHistoryResponse(BaseModel):
    """Response for scrape history endpoint."""

    jobs: list[ScrapeJobSchema]


class UserListItem(BaseModel):
    """User with message count for listing."""

    model_config = ConfigDict(from_attributes=True)

    id: Snowflake
    username: str
    discriminator: str | None = None
    global_name: str | None = None
    avatar_url: str | None = None
    bot: bool = False
    display_name: str | None = None
    message_count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class UserListResponse(BaseModel):
    """Paginated user list response."""

    users: list[UserListItem]
    total: int
    has_more: bool
    offset: int


class UserChannelActivity(BaseModel):
    """Per-channel activity for a user."""

    channel_id: Snowflake
    channel_name: str
    message_count: int


class UserMonthlyActivity(BaseModel):
    """Monthly message count for activity chart."""

    period: str
    label: str
    count: int


class UserWeeklyActivity(BaseModel):
    """Messages in one ISO week, which starts on Monday ``week``."""

    week: date
    count: int


class UserProfileSchema(BaseModel):
    """Full user profile with statistics."""

    model_config = ConfigDict(from_attributes=True)

    id: Snowflake
    username: str
    discriminator: str | None = None
    global_name: str | None = None
    avatar_url: str | None = None
    bot: bool = False
    display_name: str | None = None
    total_messages: int = 0
    total_attachments: int = 0
    total_reactions_received: int = 0
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    active_channels: int = 0
    avg_message_length: float = 0.0
    top_channels: list[UserChannelActivity] = []
    monthly_activity: list[UserMonthlyActivity] = []
    # The 52 weeks ending with the week of the last message in scope, oldest first,
    # empty weeks included.
    weekly_activity: list[UserWeeklyActivity] = []
    top_reactions_received: list[dict[str, object]] = []
    top_words: list[dict[str, object]] = []


class DownloadChannelStats(BaseModel):
    """Per-channel download statistics."""

    channel_id: Snowflake
    channel_name: str
    downloaded: int
    pending: int
    failed: int
    skipped: int
    total_images: int
    downloaded_bytes: int


class DownloadStatsResponse(BaseModel):
    """Response for download statistics endpoint."""

    total_images: int
    downloaded: int
    pending: int
    failed: int
    skipped: int
    downloaded_bytes: int
    attachments_dir: str | None = None
    channels: list[DownloadChannelStats] = []
