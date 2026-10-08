"""Tests for the one rule that turns a local attachment into a portal URL."""

from pathlib import Path

from wumpus_archiver.api.routes._helpers import local_attachment_url


class TestLocalAttachmentUrl:
    def test_served_locally_when_the_file_exists(self, tmp_path: Path) -> None:
        (tmp_path / "123").mkdir()
        (tmp_path / "123" / "photo.png").write_bytes(b"png")
        assert local_attachment_url(tmp_path, "123/photo.png") == "/attachments/123/photo.png"

    def test_none_without_an_attachments_dir(self) -> None:
        assert local_attachment_url(None, "123/photo.png") is None

    def test_none_without_a_local_path(self, tmp_path: Path) -> None:
        assert local_attachment_url(tmp_path, None) is None
        assert local_attachment_url(tmp_path, "") is None

    def test_none_when_the_file_is_missing(self, tmp_path: Path) -> None:
        assert local_attachment_url(tmp_path, "123/missing.png") is None
