"""Completed scrape model: what the archive remembers of each scrape job that completed."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from wumpus_archiver.models.base import Base


class CompletedScrape(Base):
    """One scrape job that completed against a guild, and the guild's totals when it started.

    The totals are the ones the stats route reports (``archive_reads.guild_totals``),
    taken before the job wrote anything, so the stats' change since the last scrape is
    the current totals minus these. See ``docs/adr/0004``. Times are naive UTC, as
    everywhere in the archive. A job that failed or was cancelled leaves no row.
    """

    __tablename__ = "completed_scrapes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # The guild's totals when the job started.
    messages_at_start: Mapped[int] = mapped_column(nullable=False)
    channels_at_start: Mapped[int] = mapped_column(nullable=False)
    authors_at_start: Mapped[int] = mapped_column(nullable=False)
    attachments_at_start: Mapped[int] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_completed_scrapes_guild_id_completed_at", "guild_id", "completed_at"),
    )

    def __repr__(self) -> str:
        return f"<CompletedScrape(guild={self.guild_id}, completed_at={self.completed_at})>"
