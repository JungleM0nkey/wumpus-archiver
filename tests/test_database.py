"""Tests for database connection and session management."""

import pytest

from wumpus_archiver.storage.database import Database


class TestDatabase:
    """Tests for Database class."""

    async def test_connect_disconnect(self, tmp_path) -> None:
        """Test database connect and disconnect lifecycle."""
        db = Database(f"sqlite+aiosqlite:///{tmp_path / 'lifecycle.db'}")
        await db.connect()
        assert db._engine is not None
        assert db._session_maker is not None

        await db.disconnect()
        assert db._engine is None
        assert db._session_maker is None

    async def test_create_tables(self, tmp_path) -> None:
        """Test that create_tables creates all model tables."""
        db = Database(f"sqlite+aiosqlite:///{tmp_path / 'tables.db'}")
        await db.connect()
        await db.create_tables()

        # Verify tables exist by querying metadata
        async with db.engine.connect() as conn:
            from sqlalchemy import inspect as sa_inspect

            def check_tables(sync_conn):  # type: ignore[no-untyped-def]
                inspector = sa_inspect(sync_conn)
                return inspector.get_table_names()

            tables = await conn.run_sync(check_tables)

        expected = {"guilds", "channels", "messages", "users", "attachments", "reactions"}
        assert expected.issubset(set(tables))

        await db.disconnect()

    async def test_create_tables_without_connect_raises(self) -> None:
        """Test that create_tables raises if not connected."""
        db = Database("sqlite+aiosqlite:///unused.db")
        with pytest.raises(RuntimeError, match="not connected"):
            await db.create_tables()

    async def test_session_without_connect_raises(self) -> None:
        """Test that session() raises if not connected."""
        db = Database("sqlite+aiosqlite:///unused.db")
        with pytest.raises(RuntimeError, match="not connected"):
            async with db.session():
                pass

    async def test_session_auto_commit(self, database) -> None:
        """Test that session auto-commits on successful exit."""
        from wumpus_archiver.models.guild import Guild

        async with database.session() as session:
            guild = Guild(id=9000, name="Auto Commit Test")
            session.add(guild)

        # Verify commit happened by reading in new session
        from sqlalchemy import select

        async with database.session() as session:
            result = await session.execute(select(Guild).where(Guild.id == 9000))
            guild = result.scalar_one()
            assert guild.name == "Auto Commit Test"

    async def test_session_auto_rollback_on_error(self, database) -> None:
        """Test that session auto-rolls-back on exception."""
        from wumpus_archiver.models.guild import Guild

        with pytest.raises(ValueError):
            async with database.session() as session:
                guild = Guild(id=9001, name="Rollback Test")
                session.add(guild)
                raise ValueError("Intentional error")

        # Verify rollback happened
        from sqlalchemy import select

        async with database.session() as session:
            result = await session.execute(select(Guild).where(Guild.id == 9001))
            guild = result.scalar_one_or_none()
            assert guild is None

    async def test_engine_property_raises_when_not_connected(self) -> None:
        """Test engine property raises if not connected."""
        db = Database("sqlite+aiosqlite:///unused.db")
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.engine
