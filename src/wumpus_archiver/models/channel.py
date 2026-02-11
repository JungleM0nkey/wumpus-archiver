"""Channel model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wumpus_archiver.models.base import Base

if TYPE_CHECKING:
    from wumpus_archiver.models.guild import Guild
    from wumpus_archiver.models.message import Message


class Channel(Base):
    """Discord channel model."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[int] = mapped_column(nullable=False)  # Discord channel type
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(default=0, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Archival metadata
    first_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Relationships
    guild: Mapped["Guild"] = relationship("Guild", back_populates="channels")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="channel", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (Index("ix_channels_guild_id", "guild_id"),)

    def __repr__(self) -> str:
        return f"<Channel(id={self.id}, name={self.name!r})>"
