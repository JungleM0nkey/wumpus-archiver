"""Security tests for the production SPA fallback and static file mounts.

The SPA fallback route serves files from ``portal/build`` using a URL-derived path.
These tests build a fake tree in ``tmp_path`` that has secret files *outside* the build
directory and assert that none of them can be read through any path-traversal variant.

Layout (``root`` is ``tmp_path``)::

    root/secret.txt                  <- must never be served
    root/.env                        <- must never be served
    root/outside/data.txt            <- must never be served (symlink target dir)
    root/attachments/photo.txt       <- served by the /attachments mount
    root/portal/sibling.txt          <- must never be served
    root/portal/build/index.html     <- SPA entry point
    root/portal/build/favicon.svg    <- normal asset
    root/portal/build/robots.txt
    root/portal/build/img/logo.svg
    root/portal/build/_app/immutable/app.js
    root/portal/build-evil/secret.txt  <- shares the "build" string prefix with the real dir
"""

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from wumpus_archiver.api import app as app_module
from wumpus_archiver.api.app import _resolve_portal_file

SECRET = "FAKE-SECRET-DO-NOT-SERVE-0123456789"
INDEX_HTML = "<!doctype html><title>fake portal index</title>"
ASSET_SVG = "<svg>fake-favicon</svg>"
LOGO_SVG = "<svg>fake-logo</svg>"
APP_JS = "console.log('fake app bundle');"
ROBOTS = "User-agent: *\nDisallow:\n"
PHOTO = "fake-photo-bytes"


@pytest.fixture
def site(tmp_path: Path) -> SimpleNamespace:
    """Create a fake project tree with a portal build and secrets outside of it."""
    build = tmp_path / "portal" / "build"
    (build / "img").mkdir(parents=True)
    (build / "_app" / "immutable").mkdir(parents=True)
    (build / "index.html").write_text(INDEX_HTML)
    (build / "favicon.svg").write_text(ASSET_SVG)
    (build / "robots.txt").write_text(ROBOTS)
    (build / "img" / "logo.svg").write_text(LOGO_SVG)
    (build / "_app" / "immutable" / "app.js").write_text(APP_JS)

    (tmp_path / "secret.txt").write_text(SECRET)
    (tmp_path / ".env").write_text(f"DISCORD_BOT_TOKEN={SECRET}\n")
    (tmp_path / "portal" / "sibling.txt").write_text(SECRET)
    (tmp_path / "portal" / "build-evil").mkdir()
    (tmp_path / "portal" / "build-evil" / "secret.txt").write_text(SECRET)
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "data.txt").write_text(SECRET)

    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "photo.txt").write_text(PHOTO)

    return SimpleNamespace(
        root=tmp_path,
        build=build,
        attachments=attachments,
        secret=tmp_path / "secret.txt",
    )


@pytest.fixture
def attachments_dir(site: SimpleNamespace) -> Path:
    """Serve the fake attachments directory through the shared app fixture."""
    return site.attachments


@pytest.fixture
def portal_build(site: SimpleNamespace) -> Path:
    """Serve the fake portal build through the shared app fixture."""
    return site.build


def _symlink(link: Path, target: Path) -> None:
    """Create a symlink or skip the test on platforms that cannot."""
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported here")


async def _asgi_get(app: Any, decoded_path: str) -> tuple[int, bytes]:
    """Send a GET straight to the ASGI app with an already URL-decoded ``path``.

    This bypasses HTTP client URL normalisation so literal ``..`` segments, backslashes
    and NUL bytes reach the app the way a lenient server could deliver them.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": decoded_path,
        "raw_path": decoded_path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    status = 0
    body = b""
    sent_request = False

    async def receive() -> dict[str, Any]:
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status, body
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            body += message.get("body", b"")

    await app(scope, receive, send)
    return status, body


class TestSpaServing:
    """Legitimate behaviour must keep working."""

    async def test_serves_root_index(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.text == INDEX_HTML

    async def test_serves_existing_asset(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/favicon.svg")
        assert response.status_code == 200
        assert response.text == ASSET_SVG

    async def test_serves_nested_asset(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/img/logo.svg")
        assert response.status_code == 200
        assert response.text == LOGO_SVG

    async def test_serves_robots_txt(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/robots.txt")
        assert response.status_code == 200
        assert response.text == ROBOTS

    @pytest.mark.parametrize("path", ["/archive/channels/123", "/does-not-exist.js", "/img"])
    async def test_unknown_route_and_directory_fall_back_to_index(
        self, client: httpx.AsyncClient, path: str
    ) -> None:
        response = await client.get(path)
        assert response.status_code == 200
        assert response.text == INDEX_HTML

    async def test_serves_static_app_bundle(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/_app/immutable/app.js")
        assert response.status_code == 200
        assert response.text == APP_JS


# Paths relative to the site root. Every one resolves (after decoding) to a secret outside
# portal/build, or to a sibling directory that merely shares the "build" name prefix.
TRAVERSAL_PATHS = [
    # Percent-encoded dot segments (single encoding)
    pytest.param("/%2e%2e/%2e%2e/secret.txt", id="encoded-dotdot"),
    pytest.param("/%2E%2E/%2E%2E/secret.txt", id="encoded-dotdot-uppercase"),
    pytest.param("/%2e%2e%2f%2e%2e%2fsecret.txt", id="encoded-dotdot-encoded-slash"),
    pytest.param("/..%2f..%2fsecret.txt", id="mixed-dotdot-encoded-slash"),
    pytest.param("/%2e%2e/..%2fsecret.txt", id="mixed-encoded-and-literal"),
    pytest.param("/.%2e/.%2e/secret.txt", id="half-encoded-dotdot"),
    pytest.param("/%2e%2e/%2e%2e/.env", id="dotenv"),
    pytest.param("/%2e%2e/sibling.txt", id="parent-dir-sibling"),
    pytest.param("/%2e%2e/build-evil/secret.txt", id="shared-name-prefix-sibling"),
    pytest.param("/img/%2e%2e/%2e%2e/%2e%2e/secret.txt", id="nested-then-escape"),
    # Double encoding: decoded once by the server it is just a odd filename, never twice
    pytest.param("/%252e%252e/%252e%252e/secret.txt", id="double-encoded-dotdot"),
    pytest.param("/%252e%252e%252f%252e%252e%252fsecret.txt", id="double-encoded-slash"),
    pytest.param("/..%252f..%252fsecret.txt", id="mixed-double-encoded-slash"),
    # Backslash variants
    pytest.param("/..%5c..%5csecret.txt", id="backslash-encoded"),
    pytest.param("/%2e%2e%5c%2e%2e%5csecret.txt", id="backslash-and-dotdot-encoded"),
    pytest.param("/..\\..\\secret.txt", id="backslash-literal"),
    pytest.param("/%2e%2e/..%5csecret.txt", id="backslash-mixed-with-slash"),
    # NUL bytes
    pytest.param("/%2e%2e/%2e%2e/secret.txt%00", id="nul-suffix"),
    pytest.param("/favicon.svg%00/../../secret.txt", id="nul-in-middle"),
    pytest.param("/%00", id="nul-only"),
    pytest.param("/secret.txt%00.svg", id="nul-extension-trick"),
    # Absolute-path-looking input (pathlib: `base / "/abs"` discards `base`)
    # (full URL: a bare "//host/..." would be read by httpx as a network-path reference)
    pytest.param("http://testserver//{secret}", id="double-slash-absolute"),
    pytest.param("/%2f{secret}", id="encoded-slash-absolute"),
    pytest.param("/{secret}", id="absolute-looking-without-leading-slash"),
]


class TestSpaPathTraversal:
    """No traversal variant may leak a file from outside portal/build."""

    @pytest.mark.parametrize("template", TRAVERSAL_PATHS)
    async def test_traversal_never_leaks_secret(
        self, client: httpx.AsyncClient, site: SimpleNamespace, template: str
    ) -> None:
        path = template.format(secret=str(site.secret).lstrip("/"))
        response = await client.get(path)
        assert SECRET not in response.text
        # Anything that is not a real file inside the build dir is the SPA entry point.
        assert response.status_code == 200
        assert response.text == INDEX_HTML

    @pytest.mark.parametrize(
        "decoded_path",
        [
            "/../../secret.txt",
            "/../../.env",
            "/../build-evil/secret.txt",
            "/img/../../../secret.txt",
            "/a/b/../../../../secret.txt",
            "/..\\..\\secret.txt",
            "/img\\..\\..\\..\\secret.txt",
            "/favicon.svg\x00/../../secret.txt",
            "/../../secret.txt\x00",
        ],
    )
    async def test_decoded_path_reaching_app_never_leaks_secret(
        self, app: Any, decoded_path: str
    ) -> None:
        status, body = await _asgi_get(app, decoded_path)
        assert SECRET.encode() not in body
        assert status == 200
        assert body.decode() == INDEX_HTML

    async def test_absolute_path_reaching_app_never_leaks_secret(
        self, app: Any, site: SimpleNamespace
    ) -> None:
        # "//abs/path" makes full_path absolute, which pathlib would join as-is.
        status, body = await _asgi_get(app, "/" + str(site.secret))
        assert SECRET.encode() not in body
        assert status == 200
        assert body.decode() == INDEX_HTML

    async def test_symlinked_file_pointing_outside_is_not_served(
        self, client: httpx.AsyncClient, site: SimpleNamespace
    ) -> None:
        _symlink(site.build / "leak.txt", site.secret)
        response = await client.get("/leak.txt")
        assert SECRET not in response.text
        assert response.text == INDEX_HTML

    async def test_symlinked_directory_pointing_outside_is_not_served(
        self, client: httpx.AsyncClient, site: SimpleNamespace
    ) -> None:
        _symlink(site.build / "linked", site.root / "outside")
        response = await client.get("/linked/data.txt")
        assert SECRET not in response.text
        assert response.text == INDEX_HTML

    async def test_symlink_staying_inside_build_is_still_served(
        self, client: httpx.AsyncClient, site: SimpleNamespace
    ) -> None:
        _symlink(site.build / "alias.svg", site.build / "favicon.svg")
        response = await client.get("/alias.svg")
        assert response.status_code == 200
        assert response.text == ASSET_SVG


class TestStaticMounts:
    """The /_app and /attachments StaticFiles mounts must also stay inside their roots."""

    @pytest.mark.parametrize(
        "path",
        [
            "/_app/%2e%2e/%2e%2e/%2e%2e/secret.txt",
            "/_app/..%2f..%2f..%2fsecret.txt",
            "/_app/%2e%2e%2f%2e%2e%2f%2e%2e%2fsecret.txt",
            "/_app/%252e%252e/%252e%252e/%252e%252e/secret.txt",
            "/_app/..%5c..%5c..%5csecret.txt",
            # Escapes the mount root but stays inside portal/build: still not served
            "/_app/%2e%2e/index.html",
            "/_app/..%2findex.html",
            "/attachments/%2e%2e/secret.txt",
            "/attachments/..%2fsecret.txt",
            "/attachments/%2e%2e%2fsecret.txt",
            "/attachments/%252e%252e%252fsecret.txt",
            "/attachments/..%5csecret.txt",
            "/attachments/%2e%2e/portal/sibling.txt",
        ],
    )
    async def test_traversal_is_rejected(self, client: httpx.AsyncClient, path: str) -> None:
        response = await client.get(path)
        assert SECRET not in response.text
        assert INDEX_HTML not in response.text
        assert response.status_code == 404

    async def test_attachments_serves_regular_files(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/attachments/photo.txt")
        assert response.status_code == 200
        assert response.text == PHOTO

    async def test_attachments_symlink_outside_is_not_served(
        self, client: httpx.AsyncClient, site: SimpleNamespace
    ) -> None:
        _symlink(site.attachments / "leak.txt", site.secret)
        response = await client.get("/attachments/leak.txt")
        assert SECRET not in response.text
        assert response.status_code == 404

    async def test_app_assets_symlink_outside_is_not_served(
        self, client: httpx.AsyncClient, site: SimpleNamespace
    ) -> None:
        _symlink(site.build / "_app" / "leak.txt", site.secret)
        response = await client.get("/_app/leak.txt")
        assert SECRET not in response.text
        assert response.status_code == 404


class TestResolvePortalFile:
    """Unit tests for the path-containment helper."""

    @pytest.mark.parametrize(
        ("requested", "expected"),
        [
            ("favicon.svg", "favicon.svg"),
            ("img/logo.svg", "img/logo.svg"),
            ("img/../favicon.svg", "favicon.svg"),
        ],
    )
    def test_returns_files_inside_root(
        self, site: SimpleNamespace, requested: str, expected: str
    ) -> None:
        root = site.build.resolve()
        assert _resolve_portal_file(root, requested) == root / expected

    @pytest.mark.parametrize(
        "requested",
        [
            "",
            "img",
            "missing.js",
            "../secret.txt",
            "../../secret.txt",
            "../build-evil/secret.txt",
            "img/../../../secret.txt",
            "..\\..\\secret.txt",
            "favicon.svg\x00",
            "favicon.svg\x00/../../secret.txt",
            "/etc/passwd",
        ],
    )
    def test_rejects_everything_else(self, site: SimpleNamespace, requested: str) -> None:
        assert _resolve_portal_file(site.build.resolve(), requested) is None

    def test_rejects_absolute_path_of_real_file(self, site: SimpleNamespace) -> None:
        assert _resolve_portal_file(site.build.resolve(), str(site.secret)) is None

    def test_rejects_symlink_escaping_root(self, site: SimpleNamespace) -> None:
        _symlink(site.build / "leak.txt", site.secret)
        assert _resolve_portal_file(site.build.resolve(), "leak.txt") is None

    def test_handles_symlink_loops_and_overlong_names(self, site: SimpleNamespace) -> None:
        _symlink(site.build / "loop", site.build / "loop")
        root = site.build.resolve()
        assert _resolve_portal_file(root, "loop") is None
        assert _resolve_portal_file(root, "a" * 5000) is None


# Mirrors of the request-path caps in app.py (pinned by test_caps_are_pinned below).
CHAR_CAP = 1024
SEGMENT_CAP = 64


@pytest.fixture
def resolve_calls(app: Any, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every ``Path.resolve()`` call made once the app exists.

    Depending on ``app`` guarantees ``create_app`` (which resolves the build and attachments
    directories) already ran, so only request-time calls are recorded. ``Path.resolve`` is
    quadratic in the number of path segments, so it must not run on junk requests.
    """
    calls: list[Path] = []
    real_resolve = Path.resolve

    def counting_resolve(self: Path, strict: bool = False) -> Path:
        calls.append(self)
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", counting_resolve)
    return calls


def _write(path: Path, text: str) -> Path:
    """Create ``path`` (and its parent directories) with ``text`` as content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_caps_are_pinned() -> None:
    assert app_module._MAX_REQUEST_PATH_CHARS == CHAR_CAP
    assert app_module._MAX_REQUEST_PATH_SEGMENTS == SEGMENT_CAP


class TestResolveCostIsBounded:
    """Requests that cannot be a portal file must never reach the costly ``resolve()``."""

    @pytest.mark.parametrize(
        "requested",
        [
            pytest.param("a" * (CHAR_CAP + 1), id="over-char-cap"),
            pytest.param("/".join(["a"] * (SEGMENT_CAP + 1)), id="over-segment-cap"),
            pytest.param("missing/deeper/does-not-exist.js", id="nonexistent-file"),
            pytest.param("img", id="directory"),
        ],
    )
    async def test_junk_request_falls_back_without_resolve(
        self, app: Any, resolve_calls: list[Path], requested: str
    ) -> None:
        status, body = await _asgi_get(app, "/" + requested)
        assert status == 200
        assert body.decode() == INDEX_HTML
        assert resolve_calls == []

    async def test_existing_asset_is_still_resolved_and_served(
        self, app: Any, resolve_calls: list[Path]
    ) -> None:
        status, body = await _asgi_get(app, "/img/logo.svg")
        assert status == 200
        assert body.decode() == LOGO_SVG
        assert len(resolve_calls) == 1

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param("/" + "a" * 5000, id="5000-chars"),
            pytest.param("/" + "/".join(["a"] * 30000), id="30000-segments"),
        ],
    )
    async def test_oversized_path_end_to_end_returns_index(
        self, client: httpx.AsyncClient, resolve_calls: list[Path], path: str
    ) -> None:
        response = await client.get(path)
        assert response.status_code == 200
        assert response.text == INDEX_HTML
        assert resolve_calls == []


class TestRequestPathCaps:
    """The caps are inclusive: a path exactly at the cap is served, one beyond is not."""

    def test_segment_cap_boundary(self, site: SimpleNamespace) -> None:
        root = site.build.resolve()
        within = "/".join(["d"] * (SEGMENT_CAP - 1) + ["f.txt"])
        beyond = "/".join(["d"] * SEGMENT_CAP + ["f.txt"])
        assert within.count("/") + 1 == SEGMENT_CAP
        _write(root / within, "within")
        _write(root / beyond, "beyond")
        assert _resolve_portal_file(root, within) == root / within
        assert _resolve_portal_file(root, beyond) is None

    def test_char_cap_boundary(self, site: SimpleNamespace) -> None:
        root = site.build.resolve()
        directories = "/".join(["a" * 200] * 5)  # 1004 chars, 5 segments
        within = f"{directories}/{'f' * 19}"
        beyond = f"{directories}/{'f' * 20}"
        assert len(within) == CHAR_CAP
        assert len(beyond) == CHAR_CAP + 1
        _write(root / within, "within")
        _write(root / beyond, "beyond")
        assert _resolve_portal_file(root, within) == root / within
        assert _resolve_portal_file(root, beyond) is None

    @pytest.mark.parametrize("length", [300, 1000])
    def test_single_overlong_component_is_not_found_not_an_error(
        self, site: SimpleNamespace, length: int
    ) -> None:
        """A component under the char cap but over the filesystem's name limit must not raise.

        The stat fails with ENAMETOOLONG (not one of the errors Path.is_file() swallows), so
        the function's OSError handler is what turns it into "not found" instead of a 500.
        """
        root = site.build.resolve()
        assert length <= CHAR_CAP
        assert _resolve_portal_file(root, "a" * length) is None
        assert _resolve_portal_file(root, f"d/{'b' * length}") is None


class TestNestedAssets:
    """Legitimate nested build output (SvelteKit hashed chunks, fonts) keeps working."""

    CHUNK_JS = "export const chunk = 1;"
    FONT = "fake-font-bytes"

    def test_resolves_deeply_nested_chunk(self, site: SimpleNamespace) -> None:
        root = site.build.resolve()
        chunk = _write(root / "_app" / "immutable" / "chunks" / "x.js", self.CHUNK_JS)
        assert _resolve_portal_file(root, "_app/immutable/chunks/x.js") == chunk

    async def test_serves_nested_chunk_from_static_mount(
        self, client: httpx.AsyncClient, site: SimpleNamespace
    ) -> None:
        _write(site.build / "_app" / "immutable" / "chunks" / "x.js", self.CHUNK_JS)
        response = await client.get("/_app/immutable/chunks/x.js")
        assert response.status_code == 200
        assert response.text == self.CHUNK_JS

    async def test_serves_nested_asset_from_spa_fallback(
        self, client: httpx.AsyncClient, site: SimpleNamespace
    ) -> None:
        _write(site.build / "assets" / "fonts" / "inter" / "regular.woff2", self.FONT)
        response = await client.get("/assets/fonts/inter/regular.woff2")
        assert response.status_code == 200
        assert response.text == self.FONT


class TestSymlinkedBuildDirectory:
    """``portal/build`` itself may be a symlink (e.g. a deploy that swaps release dirs)."""

    @pytest.fixture
    def linked_site(self, site: SimpleNamespace) -> SimpleNamespace:
        """Move the real build to ``root/real-dist`` and make ``portal/build`` a symlink."""
        real = site.root / "real-dist"
        site.build.rename(real)
        _symlink(site.build, real)
        # Reachable with `..` from the resolved build dir (real-dist) ...
        _write(site.root / "sibling.txt", SECRET)
        _write(site.root / "real-dist-evil" / "secret.txt", SECRET)
        # ... while root/portal/sibling.txt (from the fixture) is reachable with `..` from the
        # lexical symlink path.
        site.real = real
        return site

    @pytest.fixture
    def app(self, linked_site: SimpleNamespace, app: Any) -> Any:
        """Same app, but created only after ``portal/build`` became a symlink."""
        return app

    async def test_normal_assets_are_still_served(
        self, client: httpx.AsyncClient, linked_site: SimpleNamespace
    ) -> None:
        assert linked_site.build.is_symlink()
        for path, expected in [
            ("/", INDEX_HTML),
            ("/favicon.svg", ASSET_SVG),
            ("/img/logo.svg", LOGO_SVG),
            ("/robots.txt", ROBOTS),
            ("/_app/immutable/app.js", APP_JS),
            ("/archive/channels/123", INDEX_HTML),
        ]:
            response = await client.get(path)
            assert response.status_code == 200, path
            assert response.text == expected, path

    @pytest.mark.parametrize(
        "decoded_path",
        [
            "/../sibling.txt",
            "/../secret.txt",
            "/../.env",
            "/../portal/sibling.txt",
            "/../real-dist-evil/secret.txt",
            "/../build-evil/secret.txt",
            "/img/../../secret.txt",
            "/..\\secret.txt",
            "/../../../../../../../../secret.txt",
        ],
    )
    async def test_traversal_never_leaks_secret(self, app: Any, decoded_path: str) -> None:
        status, body = await _asgi_get(app, decoded_path)
        assert SECRET.encode() not in body
        assert status == 200
        assert body.decode() == INDEX_HTML

    @pytest.mark.parametrize(
        "path",
        [
            "/%2e%2e/sibling.txt",
            "/%2e%2e/%2e%2e/secret.txt",
            "/..%2fsecret.txt",
            "/%2e%2e/portal/sibling.txt",
        ],
    )
    async def test_encoded_traversal_never_leaks_secret(
        self, client: httpx.AsyncClient, path: str
    ) -> None:
        response = await client.get(path)
        assert SECRET not in response.text
        assert response.status_code == 200
        assert response.text == INDEX_HTML

    async def test_absolute_path_never_leaks_secret(
        self, app: Any, linked_site: SimpleNamespace
    ) -> None:
        status, body = await _asgi_get(app, "/" + str(linked_site.secret))
        assert SECRET.encode() not in body
        assert body.decode() == INDEX_HTML

    async def test_symlink_pointing_outside_is_not_served(
        self, client: httpx.AsyncClient, linked_site: SimpleNamespace
    ) -> None:
        _symlink(linked_site.build / "leak.txt", linked_site.secret)
        _symlink(linked_site.build / "linked", linked_site.root / "outside")
        for path in ("/leak.txt", "/linked/data.txt"):
            response = await client.get(path)
            assert SECRET not in response.text, path
            assert response.text == INDEX_HTML, path

    async def test_symlink_staying_inside_build_is_still_served(
        self, client: httpx.AsyncClient, linked_site: SimpleNamespace
    ) -> None:
        _symlink(linked_site.build / "alias.svg", linked_site.real / "favicon.svg")
        response = await client.get("/alias.svg")
        assert response.status_code == 200
        assert response.text == ASSET_SVG
