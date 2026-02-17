"""Guild (server) model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wumpus_archiver.models.base import Base

if TYPE_CHECKING:
    from wumpus_archiver.models.channel import Channel


class Guild(Base):
    """Discord guild (server) model."""

    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    member_count: Mapped[int | None] = mapped_column(nullable=True)

    # Archival metadata
    first_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scrape_count: Mapped[int] = mapped_column(default=0, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    channels: Mapped[list["Channel"]] = relationship(
        "Channel", back_populates="guild", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Guild(id={self.id}, name={self.name!r})>"
