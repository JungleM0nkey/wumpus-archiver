"""Tests for the archive backfill (row -> bridge payload mapping)."""

import sqlite3
from datetime import UTC, datetime

import pytest

from wumpus_archiver.bot.backfill import _channel_batches, row_payload


def _row(**over):
    base = {
        "id": 1,
        "content": "raw",
        "clean_content": "clean",
        "created_at": "2026-08-15 12:00:00.000000",
        "name": "alice_w",
        "global_name": None,
        "bot": 0,
    }
    base.update(over)
    return base


def _att(**over):
    base = {
        "message_id": 1,
        "filename": "f.png",
        "content_type": "image/png",
        "url": "https://cdn.discordapp.com/attachments/1/2/f.png",
        "width": 100,
        "height": 50,
    }
    base.update(over)
    return base


class TestRowPayload:
    def test_text_row(self):
        p = row_payload(_row(), [])
        assert p == {
            "sender": "discord-alice-w",
            "content": "clean",
            "media": None,
            "created_at": 1786795200000,
        }

    def test_bot_rows_are_skipped(self):
        assert row_payload(_row(bot=1), []) is None

    def test_empty_rows_are_skipped(self):
        assert row_payload(_row(content="", clean_content=""), []) is None

    def test_attachment_mapping(self):
        p = row_payload(_row(), [_att(), _att(url="https://cdn.discordapp.com/z.zip",
                                               filename="z.zip", content_type="application/zip")])
        assert p["media"]["url"].endswith("f.png")
        assert p["content"] == "clean\nhttps://cdn.discordapp.com/z.zip"

    def test_null_user_falls_back(self):
        p = row_payload(_row(name=None, global_name=None), [])
        assert p["sender"] == "discord-user"


@pytest.fixture()
def archive(tmp_path):
    db = sqlite3.connect(tmp_path / "a.db")
    db.executescript(
        """
        CREATE TABLE channels (id INTEGER PRIMARY KEY, guild_id INT, name TEXT,
                               type INT, parent_id INT);
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, discriminator TEXT,
                            global_name TEXT, avatar_url TEXT, bot INT);
        CREATE TABLE messages (id INTEGER PRIMARY KEY, channel_id INT, author_id INT,
                               content TEXT, clean_content TEXT, created_at TEXT);
        CREATE TABLE attachments (id INTEGER PRIMARY KEY, message_id INT, filename TEXT,
                                  content_type TEXT, url TEXT, width INT, height INT);
        INSERT INTO channels VALUES (10, 1, 'general', 0, NULL), (11, 1, 'voice', 2, NULL),
                                    (12, 1, 'a-thread', 11, 10);
        INSERT INTO users (id, username, global_name, bot) VALUES (1, "alice", "Alice", 0), (2, "botman", NULL, 1);
        INSERT INTO messages VALUES
            (100, 10, 1, 'first', 'first', '2026-01-01 00:00:00.000000'),
            (101, 10, 2, 'botmsg', 'botmsg', '2026-02-01 00:00:00.000000'),
            (102, 10, 1, 'after-cutoff', 'after-cutoff', '2026-09-01 00:00:00.000000'),
            (103, 11, 1, 'voicemsg', 'voicemsg', '2026-03-01 00:00:00.000000'),
            (104, 12, 1, 'threadmsg', 'threadmsg', '2026-03-01 00:00:00.000000');
        INSERT INTO attachments VALUES
            (1, 100, 'f.png', 'image/png', 'https://cdn.discordapp.com/f.png', 10, 10);
        """
    )
    return db


class TestChannelBatches:
    def test_filters_type_threads_bots_and_cutoff(self, archive):
        cutoff = datetime(2026, 8, 1, tzinfo=UTC)
        out = {name: msgs for name, msgs in _channel_batches(archive, 1, cutoff)}
        assert set(out) == {"general", "voice"}
        assert len(out["general"]) == 1  # bot row skipped, post-cutoff row skipped
        assert out["general"][0]["content"] == "first"
        assert out["general"][0]["media"]["url"] == "https://cdn.discordapp.com/f.png"
        assert out["general"][0]["sender"] == "discord-alice"
        assert out["voice"][0]["content"] == "voicemsg"

    def test_batches_are_chronological(self, archive):
        archive.execute(
            "INSERT INTO messages VALUES (105, 10, 1, 'later', 'later', '2026-04-01 00:00:00.000000')"
        )
        archive.commit()
        cutoff = datetime(2026, 8, 1, tzinfo=UTC)
        (name, msgs) = next(_channel_batches(archive, 1, cutoff, batch=1))
        assert [m["content"] for m in msgs] == ["first"]
