"""Shared helpers for API route handlers."""

from pathlib import Path

from fastapi import HTTPException

from wumpus_archiver.api.schemas import GalleryAttachmentSchema
from wumpus_archiver.storage.archive_reads import escape_like

__all__ = [
    "escape_like",
    "local_attachment_url",
    "raise_not_found",
    "rewrite_attachment_url",
    "rows_to_gallery_schemas",
]


def rewrite_attachment_url(
    attachments_dir: Path | None,
    local_path: str | None,
    download_status: str,
    original_url: str,
) -> str:
    """Rewrite attachment URL to local version if downloaded.

    Args:
        attachments_dir: The configured attachments directory, or None
        local_path: Relative local path from attachment record
        download_status: Download status of the attachment
        original_url: Original Discord CDN URL

    Returns:
        Local URL if downloaded and present locally, otherwise original URL
    """
    if download_status != "downloaded":
        return original_url
    return local_attachment_url(attachments_dir, local_path) or original_url


def local_attachment_url(attachments_dir: Path | None, local_path: str | None) -> str | None:
    """The portal URL of a local attachment, or ``None`` if it is not served locally.

    A local attachment is served at ``/attachments/<local_path>`` (a path relative to
    the site root; nothing here depends on the request) when an attachments dir is
    configured and the file is present in it.

    Args:
        attachments_dir: The configured attachments directory, or None
        local_path: The attachment's path relative to that directory, or None

    Returns:
        The local URL, or None when there is no attachments dir, no local path, or
        the file is missing
    """
    if attachments_dir and local_path and (attachments_dir / local_path).exists():
        return f"/attachments/{local_path}"
    return None


def raise_not_found(detail: str) -> None:
    """Raise a 404 HTTPException."""
    raise HTTPException(status_code=404, detail=detail)


def rows_to_gallery_schemas(
    attachments_dir: Path | None,
    rows: list[tuple],  # noqa: UP006
    channel_map: dict[int, str] | None = None,
) -> list[GalleryAttachmentSchema]:
    """Convert raw DB rows to GalleryAttachmentSchema list.

    Args:
        attachments_dir: The configured attachments directory, or None
        rows: Tuples of (Attachment, created_at, channel_id, username, global_name, avatar_url)
        channel_map: Optional map of channel_id -> channel_name

    Returns:
        List of GalleryAttachmentSchema
    """
    attachments = []
    for att, created_at, msg_channel_id, username, global_name, avatar_url in rows:
        url = rewrite_attachment_url(attachments_dir, att.local_path, att.download_status, att.url)
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
