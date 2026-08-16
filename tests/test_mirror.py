"""Tests for the Discord -> apehost chat mirror helpers."""

from datetime import UTC, datetime
from types import SimpleNamespace

from wumpus_archiver.bot.mirror import (
    MAX_CONTENT,
    build_payload,
    mirror_channel_name,
    sender_slug,
    user_entry,
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


def _embed(
    url: str = "",
    video_url: str = "",
    image_url: str = "",
    thumb_url: str = "",
) -> SimpleNamespace:
    video = SimpleNamespace(url=video_url, proxy_url=video_url, width=None, height=None) if video_url else None
    image = SimpleNamespace(url=image_url, proxy_url=image_url, width=None, height=None) if image_url else None
    thumb = SimpleNamespace(url=thumb_url, proxy_url=thumb_url) if thumb_url else None
    return SimpleNamespace(url=url, video=video, image=image, thumbnail=thumb)


def _message(
    author: object,
    content: str = "hi",
    clean_content: str | None = None,
    attachments: list | None = None,
    embeds: list | None = None,
    created_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        author=author,
        content=content,
        clean_content=clean_content if clean_content is not None else content,
        attachments=attachments or [],
        embeds=embeds or [],
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

    def test_video_attachment_becomes_video_media(self):
        p = build_payload(
            _message(
                _user("bob"),
                "gif via mp4",
                attachments=[_att(url="https://cdn.discordapp.com/attachments/1/2/g.mp4",
                                  filename="g.mp4", content_type="video/mp4")],
            )
        )
        assert p["media"]["type"] == "video"
        assert p["media"]["url"].endswith("g.mp4")
        assert p["content"] == "gif via mp4"

    def test_gif_attachment_typed_gif(self):
        p = build_payload(
            _message(_user("bob"), "", attachments=[_att(
                url="https://cdn.discordapp.com/attachments/1/2/g.gif",
                filename="g.gif", content_type="image/gif")])
        )
        assert p["media"]["type"] == "gif"
        assert p["content"] == ""

    def test_gifv_embed_becomes_video_media_with_poster(self):
        p = build_payload(
            _message(_user("alice"), "", embeds=[_embed(
                video_url="https://media.tenor.com/v/abc/mp4",
                thumb_url="https://media.tenor.com/v/abc/thumb.png")])
        )
        assert p["media"]["type"] == "video"
        assert p["media"]["url"] == "https://media.tenor.com/v/abc/mp4"
        assert p["media"]["thumbnail_url"] == "https://media.tenor.com/v/abc/thumb.png"
        assert p["content"] == ""

    def test_image_embed_becomes_image_media(self):
        p = build_payload(
            _message(_user("alice"), "", embeds=[_embed(
                image_url="https://i.imgur.com/x.png")])
        )
        assert p["media"]["type"] == "image"
        assert p["media"]["url"] == "https://i.imgur.com/x.png"

    def test_attachment_media_wins_over_embed(self):
        p = build_payload(
            _message(_user("bob"), "", attachments=[_att()], embeds=[_embed(
                image_url="https://i.imgur.com/y.png")])
        )
        assert p["media"]["url"].endswith("f.png")
        assert "https://i.imgur.com/y.png" in p["content"]

    def test_off_allowlist_embed_image_becomes_url_line(self):
        p = build_payload(
            _message(_user("alice"), "look", embeds=[_embed(
                url="https://example.com/article",
                image_url="https://cdn.example.com/pic.jpg")])
        )
        assert p["media"] is None
        assert "https://cdn.example.com/pic.jpg" in p["content"]
        assert "https://example.com/article" in p["content"]

    def test_embed_url_not_duplicated_when_already_in_content(self):
        p = build_payload(
            _message(_user("alice"), "see https://example.com/a",
                     embeds=[_embed(url="https://example.com/a",
                                    image_url="https://i.imgur.com/z.png")])
        )
        assert p["content"].count("https://example.com/a") == 1

    def test_embed_url_line_kept_when_not_in_content(self):
        p = build_payload(
            _message(_user("alice"), "", embeds=[_embed(url="https://example.com/b")])
        )
        assert p["content"] == "https://example.com/b"

    def test_media_only_no_content(self):
        p = build_payload(_message(_user("bob"), "", attachments=[_att()]))
        assert p["content"] == ""
        assert p["media"]["type"] == "image"

    def test_truncates_oversized_content(self):
        p = build_payload(_message(_user("alice"), "x" * (MAX_CONTENT + 100)))
        assert len(p["content"]) == MAX_CONTENT
        assert p["content"].endswith("…")


class TestUserEntry:
    def test_with_avatar(self):
        u = SimpleNamespace(
            id=1, name="alice_w", global_name="Alice Wonder",
            avatar=SimpleNamespace(url="https://cdn.discordapp.com/avatars/1/abc.png"),
        )
        assert user_entry(u) == {
            "slug": "discord-alice-wonder",
            "display_name": "Alice Wonder",
            "avatar_url": "https://cdn.discordapp.com/avatars/1/abc.png",
        }

    def test_without_avatar(self):
        u = SimpleNamespace(id=2, name="bob", global_name=None, avatar=None)
        assert user_entry(u) == {
            "slug": "discord-bob",
            "display_name": "bob",
            "avatar_url": "",
        }
