"""Tests for the dev-app module generator used by ``wumpus-archiver dev``.

``_write_dev_app_module`` writes a Python module that uvicorn imports (and therefore executes).
Paths are untrusted input as far as the generated source is concerned, so these tests check that
no path can break out of its string literal.

The hostile paths below are inert test data: the "injected" code only touches a marker file in
``tmp_path`` so a regression is detected without running anything harmful.
"""

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import SecretStr

from wumpus_archiver.api.deps import wiring_of
from wumpus_archiver.cli import _write_dev_app_module
from wumpus_archiver.compose import ServeConfig

# Placeholder swapped for a real marker path inside each hostile payload.
MARKER = "MARKER_PATH"
TOUCH_MARKER = f'__import__("pathlib").Path("{MARKER}").touch()'

HOSTILE_PATHS = {
    "double_quote_breakout": f'a"); {TOUCH_MARKER}; ("',
    "single_quote_breakout": f"a'); {TOUCH_MARKER}; ('",
    "triple_quote_breakout": f'a"""; {TOUCH_MARKER}; """',
    "newline_injection": f'a"\nimport pathlib\npathlib.Path("{MARKER}").touch()\n#',
    "carriage_return_and_tab": "a\r\tb\x0cc",
    "backslashes": "C:\\Users\\someone\\archive.db",
    "trailing_backslash": "archive\\",
    "backslash_then_quote": 'archive\\"',
    "escape_sequences_literal": "a\\n\\x41\\u0041\\N{BULLET}",
    "unicode": "дані/архів/日本語/😀.db",
    "format_braces": "a{b}c{{d}}",
    "spaces": "my archive/with spaces.db",
}

NORMAL_DB = "/var/data/archive.db"
NORMAL_ATT = "/var/data/attachments"


@pytest.fixture
def dev_module_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the generated module into ``tmp_path`` instead of the package directory.

    ``_write_dev_app_module`` derives its target from ``wumpus_archiver.cli.__file__``.

    Returns:
        Path where the generated ``_dev_app.py`` will be written.
    """
    fake_pkg = tmp_path / "pkg"
    (fake_pkg / "api").mkdir(parents=True)
    monkeypatch.setattr(sys.modules["wumpus_archiver.cli"], "__file__", str(fake_pkg / "cli.py"))
    return fake_pkg / "api" / "_dev_app.py"


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``create_app`` so importing the generated module records its arguments.

    ``serve_config`` and ``scrape_control`` are replaced too, so the generated module
    never reads the developer's environment here.

    Returns:
        Dict filled with ``database``, ``attachments_dir``, ``scrape``, ``api_auth_token``
        and ``cors_origins`` once the module is imported.
    """
    calls: dict[str, Any] = {}

    def fake_create_app(
        database: Any,
        *,
        attachments_dir: Path | None = None,
        portal_build: Path | None = None,
        scrape: Any = None,
        api_auth_token: Any = None,
        cors_origins: Any = (),
    ) -> object:
        calls["database"] = database
        calls["attachments_dir"] = attachments_dir
        calls["portal_build"] = portal_build
        calls["scrape"] = scrape
        calls["api_auth_token"] = api_auth_token
        calls["cors_origins"] = cors_origins
        return object()

    def fake_serve_config() -> ServeConfig:
        return ServeConfig(
            bot_token=SecretStr("bot-token-from-settings"),
            api_auth_token=SecretStr("api-token-from-settings"),
            cors_origins=["https://origin-from-settings.example"],
        )

    def fake_scrape_control(database: Any, bot_token: SecretStr | None) -> str:
        assert bot_token is not None
        return f"scrape-for:{database.database_url}:{bot_token.get_secret_value()}"

    monkeypatch.setattr("wumpus_archiver.api.app.create_app", fake_create_app)
    monkeypatch.setattr("wumpus_archiver.compose.serve_config", fake_serve_config)
    monkeypatch.setattr("wumpus_archiver.compose.scrape_control", fake_scrape_control)
    return calls


def _import_generated(module_path: Path) -> ModuleType:
    """Import the generated module from its file path, like uvicorn would."""
    spec = importlib.util.spec_from_file_location("_dev_app_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _string_constants(tree: ast.AST) -> set[str]:
    """Collect every string literal in a parsed module."""
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _called_names(tree: ast.AST) -> set[str]:
    """Collect the plain names of every function called in a parsed module."""
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


class TestNormalPaths:
    """The generated module is unchanged in behaviour for ordinary paths."""

    def test_module_compiles_with_expected_literals(self, dev_module_path: Path) -> None:
        """Normal paths appear as plain string literals in the generated source."""
        _write_dev_app_module(Path(NORMAL_DB), Path(NORMAL_ATT))

        source = dev_module_path.read_text(encoding="utf-8")
        compile(source, str(dev_module_path), "exec")
        tree = ast.parse(source)

        constants = _string_constants(tree)
        assert f"sqlite+aiosqlite:///{NORMAL_DB}" in constants
        assert NORMAL_ATT in constants
        assert _called_names(tree) == {
            "Database",
            "Path",
            "create_app",
            "scrape_control",
            "serve_config",
        }

    def test_import_yields_configured_app(
        self, dev_module_path: Path, captured: dict[str, Any]
    ) -> None:
        """Importing the module builds the app from the given database and attachments paths."""
        _write_dev_app_module(Path(NORMAL_DB), Path(NORMAL_ATT))

        module = _import_generated(dev_module_path)

        assert hasattr(module, "app")
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{NORMAL_DB}"
        assert captured["attachments_dir"] == Path(NORMAL_ATT)
        assert captured["portal_build"] is None
        assert captured["scrape"] == (
            f"scrape-for:sqlite+aiosqlite:///{NORMAL_DB}:bot-token-from-settings"
        )
        assert captured["api_auth_token"].get_secret_value() == "api-token-from-settings"
        assert captured["cors_origins"] == ["https://origin-from-settings.example"]

    def test_no_attachments_dir(self, dev_module_path: Path, captured: dict[str, Any]) -> None:
        """Without an attachments directory no attachments_dir argument is generated."""
        _write_dev_app_module(Path(NORMAL_DB), None)

        source = dev_module_path.read_text(encoding="utf-8")
        compile(source, str(dev_module_path), "exec")
        assert "attachments_dir" not in source
        assert _called_names(ast.parse(source)) == {
            "Database",
            "create_app",
            "scrape_control",
            "serve_config",
        }

        _import_generated(dev_module_path)
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{NORMAL_DB}"
        assert captured["attachments_dir"] is None

    def test_works_with_real_create_app(
        self,
        dev_module_path: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End to end with the real factory for ordinary paths.

        The generated module is dev's composition root and reads the bot token from the
        environment, so the test pins both to "no token" and expects read-only scrape control.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        db_path = tmp_path / "archive.db"
        att_path = tmp_path / "attachments"
        att_path.mkdir()
        _write_dev_app_module(db_path, att_path)

        module = _import_generated(dev_module_path)

        wiring = wiring_of(module.app)
        assert wiring.database.database_url == f"sqlite+aiosqlite:///{db_path}"
        assert wiring.attachments_dir == att_path.resolve()
        assert wiring.portal_build is None
        assert wiring.scrape.configured is False


@pytest.mark.parametrize("name", list(HOSTILE_PATHS))
class TestHostilePaths:
    """Hostile paths stay inside their string literals and are never executed."""

    @staticmethod
    def _hostile(name: str, marker: Path) -> Path:
        """Build the hostile path with the marker location filled in."""
        return Path(HOSTILE_PATHS[name].replace(MARKER, str(marker)))

    def test_db_path(
        self,
        name: str,
        tmp_path: Path,
        dev_module_path: Path,
        captured: dict[str, Any],
    ) -> None:
        """A hostile database path round-trips exactly and executes nothing."""
        marker = tmp_path / "pwned-db"
        hostile = self._hostile(name, marker)

        _write_dev_app_module(hostile, Path(NORMAL_ATT))

        source = dev_module_path.read_text(encoding="utf-8")
        compile(source, str(dev_module_path), "exec")
        assert _called_names(ast.parse(source)) == {
            "Database",
            "Path",
            "create_app",
            "scrape_control",
            "serve_config",
        }

        _import_generated(dev_module_path)

        assert not marker.exists(), "injected code was executed"
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{hostile}"
        assert captured["attachments_dir"] == Path(NORMAL_ATT)

    def test_attachments_dir(
        self,
        name: str,
        tmp_path: Path,
        dev_module_path: Path,
        captured: dict[str, Any],
    ) -> None:
        """A hostile attachments path round-trips exactly and executes nothing."""
        marker = tmp_path / "pwned-att"
        hostile = self._hostile(name, marker)

        _write_dev_app_module(Path(NORMAL_DB), hostile)

        source = dev_module_path.read_text(encoding="utf-8")
        compile(source, str(dev_module_path), "exec")
        assert _called_names(ast.parse(source)) == {
            "Database",
            "Path",
            "create_app",
            "scrape_control",
            "serve_config",
        }

        _import_generated(dev_module_path)

        assert not marker.exists(), "injected code was executed"
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{NORMAL_DB}"
        assert str(captured["attachments_dir"]) == str(hostile)

    def test_both_paths_hostile(
        self,
        name: str,
        tmp_path: Path,
        dev_module_path: Path,
        captured: dict[str, Any],
    ) -> None:
        """Hostile values in both literals at once still round-trip."""
        marker = tmp_path / "pwned-both"
        hostile = self._hostile(name, marker)

        _write_dev_app_module(hostile, hostile)

        _import_generated(dev_module_path)

        assert not marker.exists(), "injected code was executed"
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{hostile}"
        assert str(captured["attachments_dir"]) == str(hostile)
