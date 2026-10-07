"""Tests for the image downloader's URL, size, type and path safety checks.

No test touches the network: HTTP is replaced by a fake session whose ``get()``
returns an async context manager yielding a fake response.
"""

import asyncio
import contextlib
import hashlib
import logging
import os
import re
import stat
import threading
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import aiohttp
import pytest
from multidict import CIMultiDict

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.storage.database import Database
from wumpus_archiver.utils import downloader as downloader_module
from wumpus_archiver.utils.downloader import (
    MAX_DOWNLOAD_BYTES,
    MAX_REDIRECTS,
    ImageDownloader,
    is_allowed_url,
)

GOOD_URL = "https://cdn.discordapp.com/attachments/1/2/cat.png?ex=abc&is=def&hm=SECRETTOKEN"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-data" * 10


class FakeContent:
    """Stand-in for ``aiohttp.StreamReader`` that yields preset chunks."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.chunks_served = 0

    async def iter_chunked(self, n: int) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            self.chunks_served += 1
            yield chunk


class FakeResponse:
    """Stand-in for ``aiohttp.ClientResponse``."""

    def __init__(
        self,
        status: int = 200,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.status = status
        self.headers: CIMultiDict[str] = CIMultiDict(headers or {})
        self.content = FakeContent(chunks if chunks is not None else [PNG_BYTES])

    async def read(self) -> bytes:
        return b"".join(self.content._chunks)


class FakeRequest:
    """Async context manager returned by ``FakeSession.get``."""

    def __init__(self, response: FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> FakeResponse:
        return self._response

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeSession:
    """Stand-in for ``aiohttp.ClientSession`` serving canned responses by URL."""

    def __init__(self, routes: dict[str, FakeResponse | Exception] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeRequest:
        self.calls.append((url, kwargs))
        route = self.routes[url]
        if isinstance(route, Exception):
            raise route
        return FakeRequest(route)

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]


def png_response(**overrides: Any) -> FakeResponse:
    """Build a 200 image/png response, optionally overriding constructor args."""
    kwargs: dict[str, Any] = {"headers": {"Content-Type": "image/png"}}
    kwargs.update(overrides)
    return FakeResponse(**kwargs)


def make_attachment(
    url: str = GOOD_URL,
    proxy_url: str | None = None,
    filename: str = "cat.png",
    attachment_id: int = 42,
) -> Attachment:
    """Build a lightweight, unsaved Attachment."""
    return Attachment(
        id=attachment_id,
        message_id=1,
        filename=filename,
        content_type="image/png",
        size=len(PNG_BYTES),
        url=url,
        proxy_url=proxy_url,
        download_status="pending",
    )


def make_downloader(tmp_path: Path, **kwargs: Any) -> ImageDownloader:
    """Build a downloader over an unconnected database (never queried)."""
    database = Database("sqlite+aiosqlite:///:memory:")
    return ImageDownloader(database, tmp_path / "out", max_retries=1, **kwargs)


async def run_download(
    downloader: ImageDownloader,
    session: FakeSession,
    attachment: Attachment,
    channel_dir: Path | None = None,
) -> "tuple[str, str, int] | None":
    """Call the downloader's per-attachment method with a fake HTTP session."""
    channel_dir = channel_dir or downloader.output_dir / "100"
    channel_dir.mkdir(parents=True, exist_ok=True)
    return await downloader._download_attachment(
        cast(aiohttp.ClientSession, session), attachment, channel_dir
    )


def written_files(root: Path) -> list[Path]:
    """List every regular file below ``root``, including temp files."""
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def temp_files(root: Path) -> list[Path]:
    """List leftover ``.download-*.tmp`` files below ``root``."""
    return list(root.rglob(".download-*.tmp")) if root.exists() else []


def file_mode(path: Path) -> int:
    """Return the permission bits of ``path`` (e.g. ``0o644``)."""
    return stat.S_IMODE(path.stat().st_mode)


@contextlib.contextmanager
def process_umask(mask: int) -> Iterator[None]:
    """Set the process umask for a block and always restore the previous one."""
    previous = os.umask(mask)
    try:
        yield
    finally:
        os.umask(previous)


class TestIsAllowedUrl:
    """Table-driven tests for the URL allowlist helper."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://cdn.discordapp.com/attachments/1/2/cat.png",
            "https://cdn.discordapp.com/attachments/1/2/cat.png?ex=1&is=2&hm=3",
            "https://media.discordapp.net/attachments/1/2/cat.png?width=100",
            "https://images-ext-1.discordapp.net/external/abc/https/example.com/a.png",
            "https://CDN.DiscordApp.com/attachments/1/2/cat.png",
            "HTTPS://cdn.discordapp.com/attachments/1/2/cat.png",
            "https://cdn.discordapp.com:443/attachments/1/2/cat.png",
        ],
    )
    def test_allowed(self, url: str) -> None:
        assert is_allowed_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            # Wrong scheme
            "http://cdn.discordapp.com/attachments/1/2/cat.png",
            "file:///etc/passwd",
            "ftp://cdn.discordapp.com/cat.png",
            "//cdn.discordapp.com/cat.png",
            "cdn.discordapp.com/cat.png",
            "",
            # Lookalike hosts
            "https://evildiscordapp.com/cat.png",
            "https://cdn.evildiscordapp.com/cat.png",
            "https://discordapp.com.evil.com/cat.png",
            "https://cdn.discordapp.com.evil.com/cat.png",
            "https://cdn.discordapp.com-evil.net/cat.png",
            "https://discord.com/cat.png",
            "https://cdn.discord.com/cat.png",
            "https://discordapp.com/cat.png",
            "https://example.com/cdn.discordapp.com/cat.png",
            "https://evil.com/?u=https://cdn.discordapp.com/cat.png",
            "https://evil.com/#@cdn.discordapp.com/",
            "https://.discordapp.com/cat.png",
            "https://cdn.discordapp.com./cat.png",
            "https://cdn.discordapp.com..evil.com/cat.png",
            "https://cdn.discordapp.com%2eevil.com/cat.png",
            "https://cdn.discordаpp.com/cat.png",  # Cyrillic 'а'
            # Userinfo tricks
            "https://cdn.discordapp.com@evil.com/cat.png",
            "https://cdn.discordapp.com:pw@evil.com/cat.png",
            "https://user@cdn.discordapp.com/cat.png",
            "https://evil.com\\@cdn.discordapp.com/cat.png",
            "https://evil.com\\.cdn.discordapp.com/cat.png",
            # IP literals and internal names
            "https://127.0.0.1/cat.png",
            "https://10.0.0.5/cat.png",
            "https://192.168.1.1/cat.png",
            "https://169.254.169.254/latest/meta-data/",
            "https://[::1]/cat.png",
            "https://[fe80::1]/cat.png",
            "https://[::ffff:127.0.0.1]/cat.png",
            "https://2130706433/cat.png",
            "https://localhost/cat.png",
            "https://localhost.discordapp.com.localhost/cat.png",
            # Non-default ports
            "https://cdn.discordapp.com:8443/cat.png",
            "https://cdn.discordapp.com:80/cat.png",
            "https://cdn.discordapp.com:99999/cat.png",
            "https://cdn.discordapp.com:abc/cat.png",
            # Whitespace / control characters
            " https://cdn.discordapp.com/cat.png",
            "https://cdn.discordapp.com/cat.png ",
            "https://cdn.discordapp.com/\ncat.png",
            "https://cdn.discordapp.com\t.evil.com/cat.png",
            "https://cdn.discordapp.com/ca\x00t.png",
        ],
    )
    def test_rejected(self, url: str) -> None:
        assert is_allowed_url(url) is False


class TestBlockedUrls:
    """Disallowed URLs must never reach the network."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://cdn.discordapp.com/attachments/1/2/cat.png",
            "https://169.254.169.254/latest/meta-data/",
            "https://localhost/cat.png",
            "https://cdn.discordapp.com@evil.com/cat.png",
            "file:///etc/passwd",
        ],
    )
    async def test_blocked_host_never_calls_get(self, tmp_path: Path, url: str) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession()

        result = await run_download(downloader, session, make_attachment(url=url))

        assert result is None
        assert session.calls == []
        assert downloader.stats.failed == 1
        assert downloader.stats.downloaded == 0
        assert "not allowed" in downloader.stats.errors[0]
        assert written_files(downloader.output_dir) == []

    async def test_blocked_url_log_omits_query_string(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        downloader = make_downloader(tmp_path)
        url = "http://cdn.discordapp.com/attachments/1/2/cat.png?ex=111&is=222&hm=SECRETTOKEN"

        with caplog.at_level(logging.DEBUG, logger=downloader_module.__name__):
            await run_download(downloader, FakeSession(), make_attachment(url=url))

        assert caplog.records
        logged = caplog.text + " ".join(downloader.stats.errors)
        assert "SECRETTOKEN" not in logged
        assert "ex=111" not in logged
        assert "cdn.discordapp.com/attachments/1/2/cat.png" in logged

    async def test_blocked_url_log_omits_userinfo(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        downloader = make_downloader(tmp_path)
        url = "https://admin:hunter2@evil.example/cat.png"

        with caplog.at_level(logging.DEBUG, logger=downloader_module.__name__):
            await run_download(downloader, FakeSession(), make_attachment(url=url))

        assert "hunter2" not in caplog.text + " ".join(downloader.stats.errors)

    async def test_bad_url_falls_back_to_good_proxy_url(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        proxy = "https://media.discordapp.net/attachments/1/2/cat.png"
        session = FakeSession({proxy: png_response()})

        result = await run_download(
            downloader,
            session,
            make_attachment(url="https://169.254.169.254/x.png", proxy_url=proxy),
        )

        assert result is not None
        assert session.urls == [proxy]
        assert downloader.stats.failed == 0


class TestRedirects:
    """Redirects are followed manually and re-validated at every hop."""

    async def test_get_is_called_without_auto_redirects(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: png_response()})

        await run_download(downloader, session, make_attachment())

        assert session.calls[0][1].get("allow_redirects") is False

    async def test_redirect_to_internal_host_refused(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        internal = "http://169.254.169.254/latest/meta-data/"
        session = FakeSession(
            {
                GOOD_URL: FakeResponse(302, {"Location": internal}),
                internal: png_response(),
            }
        )

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert session.urls == [GOOD_URL]  # the internal URL was never requested
        assert downloader.stats.failed == 1
        assert "not allowed" in downloader.stats.errors[0]
        assert written_files(downloader.output_dir) == []

    @pytest.mark.parametrize(
        "location",
        [
            "https://127.0.0.1/cat.png",
            "https://evil.example/cat.png",
            "http://cdn.discordapp.com/cat.png",
            "https://cdn.discordapp.com@evil.example/cat.png",
            "//evil.example/cat.png",
            "file:///etc/passwd",
        ],
    )
    async def test_redirect_to_disallowed_location_refused(
        self, tmp_path: Path, location: str
    ) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: FakeResponse(301, {"Location": location})})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert session.urls == [GOOD_URL]
        assert downloader.stats.failed == 1

    async def test_redirect_without_location_refused(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: FakeResponse(302)})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert downloader.stats.failed == 1

    async def test_valid_redirect_followed(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        target = "https://media.discordapp.net/attachments/1/2/cat.png?ex=1"
        session = FakeSession(
            {
                GOOD_URL: FakeResponse(307, {"Location": target}),
                target: png_response(),
            }
        )

        result = await run_download(downloader, session, make_attachment())

        assert result is not None
        assert session.urls == [GOOD_URL, target]
        assert all(kwargs.get("allow_redirects") is False for _, kwargs in session.calls)

    async def test_relative_redirect_resolved_against_current_url(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        resolved = "https://cdn.discordapp.com/other/cat.png"
        session = FakeSession(
            {
                GOOD_URL: FakeResponse(302, {"Location": "/other/cat.png"}),
                resolved: png_response(),
            }
        )

        result = await run_download(downloader, session, make_attachment())

        assert result is not None
        assert session.urls == [GOOD_URL, resolved]

    async def test_redirect_loop_is_bounded(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        a = "https://cdn.discordapp.com/a.png"
        b = "https://cdn.discordapp.com/b.png"
        session = FakeSession(
            {
                a: FakeResponse(302, {"Location": b}),
                b: FakeResponse(302, {"Location": a}),
            }
        )

        result = await run_download(downloader, session, make_attachment(url=a))

        assert result is None
        assert len(session.calls) == MAX_REDIRECTS + 1
        assert downloader.stats.failed == 1
        assert "redirects" in downloader.stats.errors[0]


PROXY_URL = "https://media.discordapp.net/attachments/1/2/cat.png"

# Locations that make ``urllib.parse.urljoin`` raise ValueError
MALFORMED_LOCATIONS = [
    "http://[::1/png",
    "https://[cdn.discordapp.com/x?hm=SECRETTOKEN",
    "http://::1]/png",
    "//[::1/png",
    "http://＃@example.com/x",  # netloc invalid under NFKC normalization
]


class TestMalformedRedirect:
    """A malformed redirect Location is a refusal, never an escaping exception."""

    @pytest.mark.parametrize("location", MALFORMED_LOCATIONS)
    async def test_fetch_converts_value_error_to_rejection(
        self, tmp_path: Path, location: str
    ) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: FakeResponse(302, {"Location": location})})

        with pytest.raises(
            downloader_module._RejectedDownloadError, match="malformed redirect Location"
        ) as excinfo:
            await downloader._fetch(cast(aiohttp.ClientSession, session), GOOD_URL)

        assert location not in str(excinfo.value)  # signed URLs must not leak into messages
        assert session.urls == [GOOD_URL]

    @pytest.mark.parametrize("location", MALFORMED_LOCATIONS)
    async def test_malformed_location_falls_back_to_proxy_url(
        self, tmp_path: Path, location: str
    ) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession(
            {
                GOOD_URL: FakeResponse(302, {"Location": location}),
                PROXY_URL: png_response(),
            }
        )

        result = await run_download(downloader, session, make_attachment(proxy_url=PROXY_URL))

        assert result is not None
        assert session.urls == [GOOD_URL, PROXY_URL]
        assert (downloader.output_dir / result[0]).read_bytes() == PNG_BYTES
        assert downloader.stats.failed == 0
        assert temp_files(downloader.output_dir) == []

    @pytest.mark.parametrize("location", MALFORMED_LOCATIONS)
    async def test_malformed_location_on_both_urls_is_refused(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, location: str
    ) -> None:
        downloader = make_downloader(tmp_path)
        downloader.max_retries = 3
        session = FakeSession(
            {
                GOOD_URL: FakeResponse(302, {"Location": location}),
                PROXY_URL: FakeResponse(301, {"Location": location}),
            }
        )

        with caplog.at_level(logging.DEBUG, logger=downloader_module.__name__):
            # No exception may escape: the caller would record it as an unexpected error
            result = await run_download(downloader, session, make_attachment(proxy_url=PROXY_URL))

        assert result is None
        assert session.urls == [GOOD_URL, PROXY_URL]  # refusals are never retried
        assert downloader.stats.failed == 1
        assert downloader.stats.skipped == 0
        assert "Download refused" in downloader.stats.errors[0]
        assert "malformed redirect Location" in downloader.stats.errors[0]
        logged = caplog.text + " ".join(downloader.stats.errors)
        assert location not in logged
        assert "SECRETTOKEN" not in logged
        assert written_files(downloader.output_dir) == []

    async def test_malformed_location_without_proxy_url_is_refused(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: FakeResponse(302, {"Location": "http://[::1/png"})})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert downloader.stats.failed == 1
        assert "malformed redirect Location" in downloader.stats.errors[0]

    async def test_malformed_location_on_later_hop_is_refused(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        hop = "https://media.discordapp.net/attachments/1/2/cat.png?ex=1"
        session = FakeSession(
            {
                GOOD_URL: FakeResponse(302, {"Location": hop}),
                hop: FakeResponse(302, {"Location": "http://[::1/png"}),
            }
        )

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert session.urls == [GOOD_URL, hop]
        assert downloader.stats.failed == 1
        assert "malformed redirect Location" in downloader.stats.errors[0]


class TestSizeCap:
    """Downloads larger than ``max_bytes`` are aborted and never written."""

    async def test_default_cap_is_50_mib(self, tmp_path: Path) -> None:
        assert MAX_DOWNLOAD_BYTES == 50 * 1024 * 1024
        assert make_downloader(tmp_path).max_bytes == MAX_DOWNLOAD_BYTES

    async def test_custom_cap_via_constructor(self, tmp_path: Path) -> None:
        assert make_downloader(tmp_path, max_bytes=1234).max_bytes == 1234

    async def test_oversize_content_length_rejected_before_reading(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path, max_bytes=100)
        response = png_response(
            headers={"Content-Type": "image/png", "Content-Length": "101"},
            chunks=[b"x" * 101],
        )
        session = FakeSession({GOOD_URL: response})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert response.content.chunks_served == 0  # body never streamed
        assert downloader.stats.failed == 1
        assert "limit" in downloader.stats.errors[0]
        assert written_files(downloader.output_dir) == []

    async def test_oversize_stream_aborted_without_content_length(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path, max_bytes=100)
        chunks = [b"x" * 40 for _ in range(10)]  # 400 bytes, no Content-Length
        response = png_response(chunks=chunks)
        session = FakeSession({GOOD_URL: response})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert response.content.chunks_served == 3  # aborted as soon as 100 bytes were passed
        assert downloader.stats.failed == 1
        assert written_files(downloader.output_dir) == []

    async def test_lying_content_length_cannot_bypass_cap(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path, max_bytes=100)
        response = png_response(
            headers={"Content-Type": "image/png", "Content-Length": "10"},
            chunks=[b"x" * 60, b"x" * 60],
        )
        session = FakeSession({GOOD_URL: response})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert written_files(downloader.output_dir) == []

    async def test_exactly_at_cap_is_allowed(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path, max_bytes=100)
        session = FakeSession(
            {
                GOOD_URL: png_response(
                    headers={"Content-Type": "image/png", "Content-Length": "100"},
                    chunks=[b"x" * 50, b"x" * 50],
                )
            }
        )

        result = await run_download(downloader, session, make_attachment())

        assert result is not None
        assert result[2] == 100

    async def test_garbage_content_length_ignored(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession(
            {GOOD_URL: png_response(headers={"Content-Type": "image/png", "Content-Length": "x"})}
        )

        result = await run_download(downloader, session, make_attachment())

        assert result is not None


class TestContentType:
    """The response Content-Type must be an allowed image type."""

    @pytest.mark.parametrize(
        "content_type",
        [
            "text/html",
            "text/html; charset=utf-8",
            "application/octet-stream",
            "application/json",
            "image/svg+xml",
            "image/pngx",
            "",
        ],
    )
    async def test_wrong_content_type_rejected(self, tmp_path: Path, content_type: str) -> None:
        downloader = make_downloader(tmp_path)
        headers = {"Content-Type": content_type} if content_type else {}
        response = FakeResponse(headers=headers)
        session = FakeSession({GOOD_URL: response})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert response.content.chunks_served == 0
        assert downloader.stats.failed == 1
        assert "Content-Type" in downloader.stats.errors[0]
        assert written_files(downloader.output_dir) == []

    @pytest.mark.parametrize(
        "content_type",
        ["image/png", "IMAGE/PNG", "image/png; charset=binary", " image/jpeg ", "image/webp"],
    )
    async def test_image_content_type_accepted_ignoring_params_and_case(
        self, tmp_path: Path, content_type: str
    ) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: FakeResponse(headers={"Content-Type": content_type})})

        result = await run_download(downloader, session, make_attachment())

        assert result is not None


class TestHappyPath:
    """Legit Discord CDN downloads keep working as before."""

    async def test_download_writes_file_with_correct_hash(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: png_response(chunks=[PNG_BYTES[:20], PNG_BYTES[20:]])})

        result = await run_download(downloader, session, make_attachment())

        assert result is not None
        relative_path, content_hash, size = result
        assert relative_path == "100/42_cat.png"
        assert content_hash == hashlib.sha256(PNG_BYTES).hexdigest()
        assert size == len(PNG_BYTES)
        assert (downloader.output_dir / relative_path).read_bytes() == PNG_BYTES
        assert downloader.stats.failed == 0
        # Only the final file exists: no temp files left behind
        assert [p.name for p in written_files(downloader.output_dir)] == ["42_cat.png"]

    async def test_404_still_counts_as_skipped(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: FakeResponse(404)})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert downloader.stats.skipped == 1
        assert downloader.stats.failed == 0
        assert written_files(downloader.output_dir) == []

    async def test_server_error_counts_as_failed_after_retries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr(downloader_module.asyncio, "sleep", no_sleep)
        downloader = make_downloader(tmp_path)
        downloader.max_retries = 2
        session = FakeSession({GOOD_URL: FakeResponse(500)})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert len(session.calls) == 2  # transient errors are still retried
        assert downloader.stats.failed == 1
        assert "Failed after 2 retries" in downloader.stats.errors[0]

    async def test_network_error_is_retried(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr(downloader_module.asyncio, "sleep", no_sleep)
        downloader = make_downloader(tmp_path)
        downloader.max_retries = 2
        session = FakeSession({GOOD_URL: aiohttp.ClientConnectionError("boom")})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert len(session.calls) == 2
        assert downloader.stats.failed == 1

    async def test_rejections_are_not_retried(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        downloader.max_retries = 3
        session = FakeSession({GOOD_URL: FakeResponse(headers={"Content-Type": "text/html"})})

        await run_download(downloader, session, make_attachment())

        assert len(session.calls) == 1


class TestPathContainment:
    """Files are only ever written inside the output directory."""

    async def test_channel_dir_outside_output_dir_refused(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        outside = tmp_path / "elsewhere"
        session = FakeSession({GOOD_URL: png_response()})

        result = await run_download(downloader, session, make_attachment(), channel_dir=outside)

        assert result is None
        assert session.calls == []
        assert downloader.stats.failed == 1
        assert "outside output directory" in downloader.stats.errors[0]
        assert written_files(outside) == []

    async def test_symlinked_channel_dir_escaping_output_dir_refused(
        self, tmp_path: Path
    ) -> None:
        downloader = make_downloader(tmp_path)
        downloader.output_dir.mkdir(parents=True)
        outside = tmp_path / "secret-target"
        outside.mkdir()
        link = downloader.output_dir / "100"
        link.symlink_to(outside, target_is_directory=True)
        session = FakeSession({GOOD_URL: png_response()})

        result = await run_download(downloader, session, make_attachment(), channel_dir=link)

        assert result is None
        assert session.calls == []
        assert written_files(outside) == []
        assert downloader.stats.failed == 1

    async def test_symlinked_file_escaping_output_dir_refused(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        channel_dir = downloader.output_dir / "100"
        channel_dir.mkdir(parents=True)
        target = tmp_path / "victim.txt"
        target.write_text("original")
        (channel_dir / "42_cat.png").symlink_to(target)
        session = FakeSession({GOOD_URL: png_response()})

        result = await run_download(downloader, session, make_attachment())

        assert result is None
        assert target.read_text() == "original"
        assert downloader.stats.failed == 1

    @pytest.mark.parametrize(
        "filename",
        ["../../etc/passwd", "..\\..\\evil.png", "/etc/passwd", "..", "a/../../b.png"],
    )
    async def test_hostile_filenames_stay_inside_output_dir(
        self, tmp_path: Path, filename: str
    ) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: png_response()})

        result = await run_download(downloader, session, make_attachment(filename=filename))

        assert result is not None
        written = written_files(tmp_path)
        assert len(written) == 1
        assert written[0].resolve().is_relative_to(downloader.output_dir)
        assert (downloader.output_dir / result[0]).read_bytes() == PNG_BYTES

    async def test_failed_write_leaves_no_partial_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def failing_replace(src: object, dst: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(downloader_module.os, "replace", failing_replace)
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: png_response()})

        with pytest.raises(OSError, match="disk full"):
            await run_download(downloader, session, make_attachment())

        assert written_files(downloader.output_dir) == []


class TestFileMode:
    """Saved files get the process-umask mode, not the 0600 of a mkstemp temp file."""

    @pytest.mark.parametrize(
        ("umask", "expected_mode"),
        [
            pytest.param(0o022, 0o644, id="umask022-mode644"),
            pytest.param(0o002, 0o664, id="umask002-mode664"),
            pytest.param(0o077, 0o600, id="umask077-mode600"),
            pytest.param(0o000, 0o666, id="umask000-mode666"),
        ],
    )
    async def test_saved_file_mode_follows_umask(
        self, tmp_path: Path, umask: int, expected_mode: int
    ) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: png_response()})

        with process_umask(umask):
            result = await run_download(downloader, session, make_attachment())

        assert result is not None
        assert file_mode(downloader.output_dir / result[0]) == expected_mode

    @pytest.mark.parametrize(
        ("existing_mode", "umask", "expected_mode"),
        [
            pytest.param(0o664, 0o022, 0o644, id="was664-umask022-mode644"),
            pytest.param(0o600, 0o022, 0o644, id="was600-umask022-mode644"),
            pytest.param(0o777, 0o022, 0o644, id="was777-umask022-mode644"),
            pytest.param(0o640, 0o002, 0o664, id="was640-umask002-mode664"),
            pytest.param(0o644, 0o077, 0o600, id="was644-umask077-mode600"),
        ],
    )
    async def test_redownload_over_existing_file_uses_umask_mode(
        self, tmp_path: Path, existing_mode: int, umask: int, expected_mode: int
    ) -> None:
        downloader = make_downloader(tmp_path)
        channel_dir = downloader.output_dir / "100"
        channel_dir.mkdir(parents=True)
        target = channel_dir / "42_cat.png"
        target.write_bytes(b"old content")
        target.chmod(existing_mode)
        assert file_mode(target) == existing_mode
        session = FakeSession({GOOD_URL: png_response()})

        with process_umask(umask):
            result = await run_download(downloader, session, make_attachment())

        assert result is not None
        assert target.read_bytes() == PNG_BYTES
        assert file_mode(target) == expected_mode

    def test_umask_is_not_modified_by_writes(self, tmp_path: Path) -> None:
        # The umask is process-wide and racy with threads: writing must never touch it
        with process_umask(0o027):
            downloader_module._write_atomic(tmp_path / "a.png", PNG_BYTES)
            current = os.umask(0o027)

        assert current == 0o027


class TestTempFiles:
    """Temp files are unique per write and never left behind."""

    async def test_no_temp_file_after_success(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession({GOOD_URL: png_response()})

        result = await run_download(downloader, session, make_attachment())

        assert result is not None
        assert temp_files(downloader.output_dir) == []
        assert [p.name for p in written_files(downloader.output_dir)] == ["42_cat.png"]

    async def test_no_temp_file_after_refusal(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        session = FakeSession(
            {
                GOOD_URL: FakeResponse(302, {"Location": "http://[::1/png"}),
                PROXY_URL: FakeResponse(headers={"Content-Type": "text/html"}),
            }
        )

        result = await run_download(downloader, session, make_attachment(proxy_url=PROXY_URL))

        assert result is None
        assert downloader.stats.failed == 1
        assert temp_files(downloader.output_dir) == []
        assert written_files(downloader.output_dir) == []

    @pytest.mark.parametrize(
        "failure",
        [OSError("disk full"), KeyboardInterrupt()],
        ids=["oserror", "keyboardinterrupt"],
    )
    def test_no_temp_file_after_replace_failure_and_destination_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException
    ) -> None:
        target = tmp_path / "42_cat.png"
        target.write_bytes(b"old content")

        def failing_replace(src: object, dst: object) -> None:
            raise failure

        monkeypatch.setattr(downloader_module.os, "replace", failing_replace)

        with pytest.raises(type(failure)):
            downloader_module._write_atomic(target, PNG_BYTES)

        assert target.read_bytes() == b"old content"
        assert list(tmp_path.iterdir()) == [target]

    def test_no_temp_file_after_fdopen_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def failing_fdopen(fd: int, *args: object, **kwargs: object) -> object:
            os.close(fd)
            raise OSError("fdopen failed")

        monkeypatch.setattr(downloader_module.os, "fdopen", failing_fdopen)

        with pytest.raises(OSError, match="fdopen failed"):
            downloader_module._write_atomic(tmp_path / "42_cat.png", PNG_BYTES)

        assert list(tmp_path.iterdir()) == []

    def test_no_temp_file_after_write_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class ExplodingFile:
            def __init__(self, fd: int) -> None:
                self._fd = fd

            def __enter__(self) -> "ExplodingFile":
                return self

            def __exit__(self, *exc_info: object) -> None:
                os.close(self._fd)

            def write(self, data: bytes) -> int:
                raise OSError("write failed")

        monkeypatch.setattr(
            downloader_module.os, "fdopen", lambda fd, *args, **kwargs: ExplodingFile(fd)
        )

        with pytest.raises(OSError, match="write failed"):
            downloader_module._write_atomic(tmp_path / "42_cat.png", PNG_BYTES)

        assert list(tmp_path.iterdir()) == []

    def test_concurrent_writes_to_one_directory_do_not_collide(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workers = 16
        opened: list[Path] = []
        lock = threading.Lock()
        real_open = os.open

        def recording_open(path: Any, flags: int, mode: int = 0o777, **kwargs: Any) -> int:
            if Path(path).name.startswith(".download-"):
                with lock:
                    opened.append(Path(path))
            return real_open(path, flags, mode, **kwargs)

        monkeypatch.setattr(downloader_module.os, "open", recording_open)
        barrier = threading.Barrier(workers)

        def write(index: int) -> None:
            barrier.wait(timeout=10)  # start every write at the same moment
            downloader_module._write_atomic(
                tmp_path / f"{index}_cat.png", PNG_BYTES + str(index).encode()
            )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in [pool.submit(write, index) for index in range(workers)]:
                future.result(timeout=30)

        for index in range(workers):
            assert (tmp_path / f"{index}_cat.png").read_bytes() == PNG_BYTES + str(index).encode()
        assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
            f"{index}_cat.png" for index in range(workers)
        )
        # One temp file per write, each unique, unpredictable and beside its destination
        assert len(opened) == workers
        assert len({p.name for p in opened}) == workers
        assert all(p.parent == tmp_path for p in opened)
        assert all(re.fullmatch(r"\.download-[0-9A-Za-z]{16,}\.tmp", p.name) for p in opened)

    async def test_concurrent_downloads_into_one_channel_dir(self, tmp_path: Path) -> None:
        downloader = make_downloader(tmp_path)
        count = 12
        routes: dict[str, FakeResponse | Exception] = {}
        attachments = []
        for index in range(1, count + 1):
            url = f"https://cdn.discordapp.com/attachments/1/{index}/cat.png"
            routes[url] = png_response(chunks=[PNG_BYTES + str(index).encode()])
            attachments.append(make_attachment(url=url, attachment_id=index))
        session = FakeSession(routes)
        channel_dir = downloader.output_dir / "100"
        channel_dir.mkdir(parents=True)

        results = await asyncio.gather(
            *(
                downloader._download_attachment(
                    cast(aiohttp.ClientSession, session), attachment, channel_dir
                )
                for attachment in attachments
            )
        )

        assert all(result is not None for result in results)
        assert downloader.stats.failed == 0
        for index in range(1, count + 1):
            saved = channel_dir / f"{index}_cat.png"
            assert saved.read_bytes() == PNG_BYTES + str(index).encode()
        assert temp_files(downloader.output_dir) == []
        assert len(written_files(downloader.output_dir)) == count


class TestDownloadAllImages:
    """End to end through the database with a fake HTTP session."""

    async def test_blocked_and_good_attachments(
        self, database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime.now(UTC)
        async with database.session() as db_session:
            db_session.add(Guild(id=9000, name="Guild"))
            await db_session.flush()
            db_session.add(Channel(id=9001, guild_id=9000, name="pics", type=0))
            await db_session.flush()
            db_session.add(
                Message(
                    id=9002,
                    channel_id=9001,
                    content="",
                    clean_content="",
                    created_at=now,
                    scraped_at=now,
                )
            )
            await db_session.flush()
            for att_id, name, url in (
                (9100, "good.png", GOOD_URL),
                (9101, "bad.png", "https://169.254.169.254/latest/meta-data/"),
            ):
                db_session.add(
                    Attachment(
                        id=att_id,
                        message_id=9002,
                        filename=name,
                        content_type="image/png",
                        size=len(PNG_BYTES),
                        url=url,
                        download_status="pending",
                    )
                )

        fake_session = FakeSession({GOOD_URL: png_response()})

        class FakeClientSession:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> FakeSession:
                return fake_session

            async def __aexit__(self, *exc_info: object) -> None:
                return None

        monkeypatch.setattr(downloader_module.aiohttp, "ClientSession", FakeClientSession)

        downloader = ImageDownloader(database, tmp_path / "out", max_retries=1)
        stats = await downloader.download_all_images()

        assert stats.total == 2
        assert stats.downloaded == 1
        assert stats.failed == 1
        assert stats.total_bytes == len(PNG_BYTES)
        assert fake_session.urls == [GOOD_URL]
        assert (tmp_path / "out" / "9001" / "9100_good.png").read_bytes() == PNG_BYTES
        assert not (tmp_path / "out" / "9001" / "9101_bad.png").exists()

        async with database.session() as db_session:
            good = await db_session.get(Attachment, 9100)
            bad = await db_session.get(Attachment, 9101)
        assert good is not None
        assert good.download_status == "downloaded"
        assert good.local_path == "9001/9100_good.png"
        assert good.content_hash == hashlib.sha256(PNG_BYTES).hexdigest()
        assert bad is not None
        assert bad.download_status != "downloaded"
        assert bad.local_path is None
