"""Shared helpers for API route handlers."""

from pathlib import Path

from fastapi import HTTPException, Request
from sqlalchemy import or_

from wumpus_archiver.api.schemas import (
    AttachmentSchema,
    GalleryAttachmentSchema,
)
from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.storage.database import Database


def get_db(request: Request) -> Database:
    """Get the active database from the registry."""
    registry = getattr(request.app.state, "db_registry", None)
    if registry is not None:
        return registry.get_active()
    return request.app.state.database  # type: ignore[no-any-return]


def get_attachments_path(request: Request) -> Path | None:
    """Get local attachments path from app state."""
    return getattr(request.app.state, "attachments_path", None)


def rewrite_attachment_url(
    request: Request,
    local_path: str | None,
    download_status: str,
    original_url: str,
) -> str:
    """Rewrite attachment URL to local version if downloaded.

    Args:
        request: Current request (for base URL)
        local_path: Relative local path from attachment record
        download_status: Download status of the attachment
        original_url: Original Discord CDN URL

    Returns:
        Local URL if downloaded, otherwise original URL
    """
    attachments_dir = get_attachments_path(request)
    if (
        attachments_dir
        and local_path
        and download_status == "downloaded"
        and (attachments_dir / local_path).exists()
    ):
        return f"/attachments/{local_path}"
    return original_url


def rewrite_attachment_schema(request: Request, schema: AttachmentSchema) -> AttachmentSchema:
    """Rewrite URLs in an AttachmentSchema if local file exists."""
    # We need to query the DB for local_path — but schemas don't have it.
    # Instead the caller should pass the ORM object data.
    return schema


def raise_not_found(detail: str) -> None:
    """Raise a 404 HTTPException."""
    raise HTTPException(status_code=404, detail=detail)


IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/avif")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".tiff"}


def looks_like_image(content_type: str | None, filename: str) -> bool:
    """Check if an attachment is an image by content_type or file extension."""
    if content_type and content_type.startswith("image/"):
        return True
    ext = Path(filename).suffix.lower()
    return ext in IMAGE_EXTENSIONS


def image_filter():
    """SQLAlchemy filter for image attachments (by content_type or file extension)."""
    return or_(
        Attachment.content_type.in_(IMAGE_TYPES),
        *[Attachment.filename.ilike(f"%{ext}") for ext in IMAGE_EXTENSIONS],
    )


def rows_to_gallery_schemas(
    request: Request,
    rows: list[tuple],  # type: ignore[type-arg]
    channel_map: dict[int, str] | None = None,
) -> list[GalleryAttachmentSchema]:
    """Convert raw DB rows to GalleryAttachmentSchema list.

    Args:
        request: Current request for URL rewriting
        rows: Tuples of (Attachment, created_at, channel_id, username, global_name, avatar_url)
        channel_map: Optional map of channel_id -> channel_name

    Returns:
        List of GalleryAttachmentSchema
    """
    attachments = []
    for att, created_at, msg_channel_id, username, global_name, avatar_url in rows:
        url = rewrite_attachment_url(
            request, att.local_path, att.download_status, att.url
        )
        proxy_url = att.proxy_url
        if url != att.url:
            proxy_url = None
        attachments.append(
            GalleryAttachmentSchema(
                id=att.id,
                message_id=att.message_id,
                filename=att.filename,
                content_type=att.content_type,
                size=att.size,
                url=url,
                proxy_url=proxy_url,
                width=att.width,
                height=att.height,
                created_at=created_at,
                author_name=global_name or username,
                author_avatar_url=avatar_url,
                channel_id=msg_channel_id,
                channel_name=channel_map.get(msg_channel_id) if channel_map else None,
            )
        )
    return attachments
