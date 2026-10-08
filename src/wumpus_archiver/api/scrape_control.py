"""Scrape control: the port the scrape routes talk to, and the job it reports on.

This module imports pydantic only. The production adapter, ``ScrapeJobManager`` in
``scrape_manager.py``, is the one place under ``api/`` that reaches Discord, and it
does so only once a job actually starts.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class JobStatus(str, Enum):
    """Scrape job status."""

    PENDING = "pending"
    CONNECTING = "connecting"
    SCRAPING = "scraping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScrapeChannelProgress(BaseModel):
    """One channel of a scrape job: its id and name, the messages written so far, and whether
    it is done."""

    id: int
    name: str
    messages: int = 0
    done: bool = False


class ScrapeProgress(BaseModel):
    """Progress data for a running scrape job."""

    current_channel: str = ""
    channels_done: int = 0
    messages_scraped: int = 0
    attachments_found: int = 0
    errors: list[str] = []
    # The channels the job has reported, in the order it reached them.
    channels: list[ScrapeChannelProgress] = []

    def record_channel(self, channel_id: int, name: str, messages: int) -> None:
        """Record the scraper's report that ``messages`` messages of a channel are written.

        The scraper works through one channel at a time, so a report for a channel
        other than the last one reported means that one is done. The live totals
        follow: channels done, and messages across every channel reported. Channels
        are told apart by id: Discord lets two channels share a name.
        """
        last = self.channels[-1] if self.channels else None
        if last is None or last.id != channel_id:
            if last is not None:
                last.done = True
            last = ScrapeChannelProgress(id=channel_id, name=name)
            self.channels.append(last)
        last.messages = messages
        self.current_channel = name
        self.channels_done = sum(1 for c in self.channels if c.done)
        self.messages_scraped = sum(c.messages for c in self.channels)

    def finish_channels(self) -> None:
        """Mark every channel reported done: the job got through all of them."""
        for channel in self.channels:
            channel.done = True
        self.channels_done = len(self.channels)


class ScrapeJob(BaseModel):
    """Represents a single scrape job."""

    id: str
    guild_id: int
    status: JobStatus = JobStatus.PENDING
    progress: ScrapeProgress = ScrapeProgress()
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None


@runtime_checkable
class ScrapeControl(Protocol):
    """Everything the ``/api/scrape`` routes may ask of scrape control.

    Invariants every adapter keeps:

    - ``configured`` is fixed for the adapter's lifetime. It is the one predicate
      behind the ``has_token`` field of the status response and behind the 400
      on ``/scrape/start``.
    - When not configured: ``current_job`` is ``None``, ``history`` is empty and
      ``cancel()`` returns ``False``.
    - ``history`` is most recent first and never contains the job that is busy.
    - ``start_scrape`` is legal only when configured and not busy; it raises
      ``RuntimeError`` otherwise. Routes check first so callers see 400 or 409,
      never the exception.
    """

    @property
    def configured(self) -> bool: ...

    @property
    def is_busy(self) -> bool: ...

    @property
    def current_job(self) -> ScrapeJob | None: ...

    @property
    def history(self) -> list[ScrapeJob]: ...

    def start_scrape(self, guild_id: int) -> ScrapeJob: ...

    def cancel(self) -> bool: ...


class ReadOnlyScrape:
    """Scrape control without a bot token: reports nothing and starts nothing.

    This is what the app runs with whenever no token was configured, and the
    default the test fixtures build with, so both go through the same object.
    """

    configured: bool = False
    is_busy: bool = False
    current_job: ScrapeJob | None = None

    @property
    def history(self) -> list[ScrapeJob]:
        return []

    def start_scrape(self, guild_id: int) -> ScrapeJob:
        raise RuntimeError("scrape control is read-only: no bot token was configured")

    def cancel(self) -> bool:
        return False


__all__ = [
    "JobStatus",
    "ReadOnlyScrape",
    "ScrapeChannelProgress",
    "ScrapeControl",
    "ScrapeJob",
    "ScrapeProgress",
]
