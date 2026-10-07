"""Direct tests for archive reads (``wumpus_archiver.storage.archive_reads``)."""

import pytest

from wumpus_archiver.storage.archive_reads import MediaKind, escape_like


class TestMediaKind:
    """The one home of the media content-type lists."""

    def test_image_types(self) -> None:
        assert MediaKind.IMAGE.content_types == (
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "image/avif",
        )

    def test_gif_types(self) -> None:
        assert MediaKind.GIF.content_types == ("image/gif",)

    def test_video_types(self) -> None:
        assert MediaKind.VIDEO.content_types == ("video/mp4", "video/webm", "video/quicktime")

    def test_gif_is_a_distinct_kind_although_images_include_gifs(self) -> None:
        assert MediaKind.GIF is not MediaKind.IMAGE
        assert set(MediaKind.GIF.content_types) < set(MediaKind.IMAGE.content_types)


def test_escape_like_is_still_importable_from_the_route_helpers() -> None:
    from wumpus_archiver.api.routes._helpers import escape_like as reexported

    assert reexported is escape_like


class TestEscapeLike:
    """Unit tests for escape_like."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("", ""),
            ("plain text", "plain text"),
            ("%", "\\%"),
            ("_", "\\_"),
            ("\\", "\\\\"),
            ("100%_real", "100\\%\\_real"),
            ("%_%", "\\%\\_\\%"),
            # The escape character must be escaped first, so it is not double-processed.
            ("a\\%", "a\\\\\\%"),
            ("a\\_b", "a\\\\\\_b"),
        ],
    )
    def test_default_escape(self, value: str, expected: str) -> None:
        """Test that %, _ and the backslash are each prefixed with a backslash."""
        assert escape_like(value) == expected

    def test_custom_escape_character(self) -> None:
        """Test escaping with a non-default escape character."""
        assert escape_like("a!b%c_d", escape="!") == "a!!b!%c!_d"

    def test_backslash_is_not_special_with_custom_escape(self) -> None:
        """Test that a backslash is left alone when another escape character is used."""
        assert escape_like("a\\b", escape="!") == "a\\b"
