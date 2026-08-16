"""Tests for the Discord -> apehost chat mirror helpers."""

from datetime import UTC, datetime
from types import SimpleNamespace

from wumpus_archiver.bot.mirror import (
    MAX_CONTENT,
    build_payload,
    mirror_channel_name,
    sender_slug,
)


def _user(name: str = "", global_name: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, global_name=global_name)


def _att(
    url: str = "https://cdn.discordapp.com/attachments/1/2/f.png",
    filename: str = "f.png",
    content_type: str | None = "image/png",
    width: int | None = 100,
    height: int | None = 50,
) -> SimpleNamespace:
    return SimpleNamespace(
        url=url, filename=filename, content_type=content_type, width=width, height=height
    )


def _message(
    author: object,
    content: str = "hi",
    clean_content: str | None = None,
    attachments: list | None = None,
    created_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        author=author,
        content=content,
        clean_content=clean_content if clean_content is not None else content,
        attachments=attachments or [],
        created_at=created_at or datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )


class TestSenderSlug:
    def test_prefers_global_name(self):
        assert sender_slug("alice_w", "Alice Wonder") == "discord-alice-wonder"

    def test_sanitizes_username(self):
        assert sender_slug("Bob.The-Builder_99") == "discord-bob-the-builder-99"

    def test_collapses_and_trims_separators(self):
        assert sender_slug("!!___---___carol---___!!") == "discord-carol"

    def test_falls_back_when_name_is_junk(self):
        assert sender_slug("!!!") == "discord-user"
        assert sender_slug("") == "discord-user"

    def test_caps_length(self):
        slug = sender_slug("x" * 100)
        assert len(slug) <= len("discord-") + 32
        assert slug.startswith("discord-")


class TestMirrorChannelName:
    def test_prefixes_and_caps(self):
        assert mirror_channel_name("general") == "discord-general"
        assert len(mirror_channel_name("c" * 100)) <= 64


class TestBuildPayload:
    def test_text_only(self):
        p = build_payload(_message(_user("alice"), "hello @all"))
        assert p == {
            "sender": "discord-alice",
            "content": "hello @all",
            "media": None,
            "created_at": 1786795200000,  # 2026-08-15T12:00:00Z
        }

    def test_empty_message_is_none(self):
        assert build_payload(_message(_user("alice"), "  ")) is None
        assert build_payload(_message(_user("alice"), "")) is None

    def test_image_attachment_becomes_media(self):
        p = build_payload(_message(_user("bob"), "look", attachments=[_att()]))
        assert p["media"] == {
            "url": "https://cdn.discordapp.com/attachments/1/2/f.png",
            "thumbnail_url": "https://cdn.discordapp.com/attachments/1/2/f.png",
            "type": "image",
            "width": 100,
            "height": 50,
            "alt": "f.png",
        }
        assert p["content"] == "look"

    def test_extra_attachments_become_url_lines(self):
        p = build_payload(
            _message(
                _user("bob"),
                "two files",
                attachments=[_att(), _att(url="https://cdn.discordapp.com/a/b/data.zip",
                                          filename="data.zip", content_type="application/zip")],
            )
        )
        assert p["media"]["alt"] == "f.png"
        assert p["content"] == "two files\nhttps://cdn.discordapp.com/a/b/data.zip"

    def test_non_image_only_goes_into_content(self):
        p = build_payload(
            _message(_user("bob"), "", attachments=[_att(content_type="video/mp4")])
        )
        assert p["media"] is None
        assert p["content"] == "https://cdn.discordapp.com/attachments/1/2/f.png"

    def test_media_only_no_content(self):
        p = build_payload(_message(_user("bob"), "", attachments=[_att()]))
        assert p["content"] == ""
        assert p["media"]["type"] == "image"

    def test_truncates_oversized_content(self):
        p = build_payload(_message(_user("alice"), "x" * (MAX_CONTENT + 100)))
        assert len(p["content"]) == MAX_CONTENT
        assert p["content"].endswith("…")
