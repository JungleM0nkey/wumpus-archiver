"""Message model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wumpus_archiver.models.base import Base

if TYPE_CHECKING:
    from wumpus_archiver.models.attachment import Attachment
    from wumpus_archiver.models.channel import Channel
    from wumpus_archiver.models.reaction import Reaction
    from wumpus_archiver.models.user import User


class Message(Base):
    """Discord message model."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("channels.id"), nullable=False)
    author_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Message content
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    clean_content: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Message metadata
    pinned: Mapped[bool] = mapped_column(default=False, nullable=False)
    tts: Mapped[bool] = mapped_column(default=False, nullable=False)
    mention_everyone: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Embeds and components stored as JSON (simplified)
    embeds: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Reference to parent message (for replies/threads)
    reference_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Archival metadata
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="messages")
    author: Mapped[Optional["User"]] = relationship("User", back_populates="messages")
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment", back_populates="message", cascade="all, delete-orphan"
    )
    reactions: Mapped[list["Reaction"]] = relationship(
        "Reaction", back_populates="message", cascade="all, delete-orphan"
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_messages_channel_id_created_at", "channel_id", "created_at"),
        Index("ix_messages_author_id", "author_id"),
        Index("ix_messages_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, author={self.author_id}, content={content_preview!r})>"
