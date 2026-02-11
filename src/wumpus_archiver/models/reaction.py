"""Reaction model."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wumpus_archiver.models.base import Base

if TYPE_CHECKING:
    from wumpus_archiver.models.message import Message


class Reaction(Base):
    """Discord reaction model."""

    __tablename__ = "reactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id"), nullable=False)

    # Emoji data
    emoji_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    emoji_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    emoji_animated: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Count of reactions (not individual user records for privacy/efficiency)
    count: Mapped[int] = mapped_column(default=1, nullable=False)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="reactions")

    # Indexes
    __table_args__ = (Index("ix_reactions_message_id", "message_id"),)

    def __repr__(self) -> str:
        emoji = self.emoji_name or f":{self.emoji_id}:"
        return f"<Reaction(message={self.message_id}, emoji={emoji!r}, count={self.count})>"

    @property
    def emoji_display(self) -> str:
        """Return the displayable emoji."""
        if self.emoji_name:
            return self.emoji_name
        return f"<:{self.emoji_id}>"
