"""Attachment model."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wumpus_archiver.models.base import Base

if TYPE_CHECKING:
    from wumpus_archiver.models.message import Message


class Attachment(Base):
    """Discord attachment model."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id"), nullable=False)

    # File metadata
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes

    # URLs
    url: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Dimensions (for images/videos)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Local storage (if downloaded)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, downloaded, failed, skipped

    # Content hash for deduplication
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="attachments")

    # Indexes
    __table_args__ = (Index("ix_attachments_message_id", "message_id"),)

    def __repr__(self) -> str:
        return f"<Attachment(id={self.id}, filename={self.filename!r}, size={self.size})>"

    @property
    def is_image(self) -> bool:
        """Check if attachment is an image."""
        if self.content_type:
            return self.content_type.startswith("image/")
        return False

    @property
    def is_video(self) -> bool:
        """Check if attachment is a video."""
        if self.content_type:
            return self.content_type.startswith("video/")
        return False
