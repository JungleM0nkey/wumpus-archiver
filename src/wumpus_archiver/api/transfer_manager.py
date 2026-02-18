"""Background data transfer manager for SQLite → PostgreSQL migration."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import DatabaseRegistry

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000

# Transfer order: respects foreign key dependencies
TABLES = [
    ("guilds", Guild),
    ("users", User),
    ("channels", Channel),
    ("messages", Message),
    ("attachments", Attachment),
    ("reactions", Reaction),
]


@dataclass
class TransferJob:
    """Tracks progress of a data transfer."""

    status: str = "pending"  # pending | running | completed | failed | cancelled
    current_table: str = ""
    tables_done: int = 0
    tables_total: int = len(TABLES)
    rows_transferred: int = 0
    total_rows: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TransferManager:
    """Manages background data transfers between database sources."""

    def __init__(self, registry: DatabaseRegistry) -> None:
        self._registry = registry
        self._job: TransferJob | None = None
        self._task: asyncio.Task[None] | None = None
        self._cancel_event = asyncio.Event()

    @property
    def current_job(self) -> TransferJob | None:
        return self._job

    @property
    def is_busy(self) -> bool:
        return self._job is not None and self._job.status in ("pending", "running")

    def start_transfer(self, source: str, target: str) -> TransferJob:
        """Start a background transfer from source to target database.

        Args:
            source: Registry name of the source database (e.g. "sqlite")
            target: Registry name of the target database (e.g. "postgres")

        Returns:
            The created TransferJob

        Raises:
            RuntimeError: If a transfer is already running
            KeyError: If source or target is not registered
        """
        if self.is_busy:
            raise RuntimeError("A transfer is already running")

        # Validate source and target exist
        src_db = self._registry.sources[source]
        tgt_db = self._registry.sources[target]

        job = TransferJob(started_at=datetime.now(UTC))
        self._job = job
        self._cancel_event.clear()

        self._task = asyncio.create_task(self._run_transfer(job, src_db, tgt_db))
        return job

    def cancel(self) -> bool:
        """Request cancellation of the current transfer."""
        if not self.is_busy or self._job is None:
            return False
        self._cancel_event.set()
        return True

    async def _run_transfer(self, job: TransferJob, src_db, tgt_db) -> None:
        """Execute the transfer in the background."""
        try:
            job.status = "running"
            logger.info("Transfer started")

            # Phase 1: Count total rows across all tables
            async with src_db.session() as session:
                for _table_name, model in TABLES:
                    result = await session.execute(select(func.count()).select_from(model))
                    job.total_rows += result.scalar_one()

            logger.info("Total rows to transfer: %d", job.total_rows)

            # Phase 2: Transfer each table
            for table_name, model in TABLES:
                if self._cancel_event.is_set():
                    job.status = "cancelled"
                    job.finished_at = datetime.now(UTC)
                    logger.info("Transfer cancelled during %s", table_name)
                    return

                job.current_table = table_name
                logger.info("Transferring table: %s", table_name)

                await self._transfer_table(job, src_db, tgt_db, model)
                job.tables_done += 1

            # Phase 3: Reset PostgreSQL sequences for auto-increment columns.
            # After transferring data with explicit IDs, sequences may be behind
            # the max existing ID, causing UniqueViolation on next insert.
            await self._reset_sequences(tgt_db)

            job.status = "completed"
            job.finished_at = datetime.now(UTC)
            logger.info(
                "Transfer completed: %d rows in %d tables",
                job.rows_transferred,
                job.tables_done,
            )

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            logger.info("Transfer cancelled")

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.finished_at = datetime.now(UTC)
            logger.error("Transfer failed: %s", e)

    async def _transfer_table(self, job, src_db, tgt_db, model) -> None:
        """Transfer all rows of a single table in batches."""
        offset = 0

        while True:
            if self._cancel_event.is_set():
                return

            # Read batch from source
            async with src_db.session() as src_session:
                result = await src_session.execute(
                    select(model).offset(offset).limit(BATCH_SIZE)
                )
                rows = list(result.scalars().all())

                if not rows:
                    break

                # Detach rows from source session so we can use them in target
                for row in rows:
                    src_session.expunge(row)

            # Write batch to target (merge = upsert: insert new, update existing)
            inserted = 0
            updated = 0
            async with tgt_db.session() as tgt_session:
                for row in rows:
                    existing = await tgt_session.get(type(row), row.id)
                    if existing is not None:
                        updated += 1
                    else:
                        inserted += 1
                    await tgt_session.merge(row)

            job.rows_transferred += len(rows)
            offset += len(rows)

            logger.debug(
                "  %s: transferred %d rows (inserted=%d, updated=%d, offset %d)",
                model.__tablename__,
                len(rows),
                inserted,
                updated,
                offset - len(rows),
            )

    async def _reset_sequences(self, tgt_db) -> None:  # type: ignore[no-untyped-def]
        """Reset PostgreSQL sequences for tables with auto-increment PKs.

        After bulk-inserting data with explicit IDs, PostgreSQL sequences
        may be behind the max existing ID. This resets them to avoid
        UniqueViolation errors on subsequent inserts.
        """
        url = str(tgt_db.engine.url)
        if "postgresql" not in url:
            return

        # Tables with auto-increment integer PKs (not snowflake BigInteger PKs)
        auto_increment_tables = ["reactions"]

        async with tgt_db.session() as session:
            for table in auto_increment_tables:
                try:
                    await session.execute(
                        text(f"SELECT setval('{table}_id_seq', COALESCE((SELECT MAX(id) FROM {table}), 1))")
                    )
                    await session.commit()
                    logger.info("Reset sequence for %s", table)
                except Exception as e:
                    logger.warning("Failed to reset sequence for %s: %s", table, e)
