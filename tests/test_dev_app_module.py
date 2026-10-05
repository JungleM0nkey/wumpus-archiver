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

from wumpus_archiver.cli import _write_dev_app_module

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

    Returns:
        Dict filled with ``database`` and ``attachments_path`` once the module is imported.
    """
    calls: dict[str, Any] = {}

    def fake_create_app(
        database: Any,
        attachments_path: Path | None = None,
        discord_token: str | None = None,
    ) -> object:
        calls["database"] = database
        calls["attachments_path"] = attachments_path
        return object()

    monkeypatch.setattr("wumpus_archiver.api.app.create_app", fake_create_app)
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
        assert _called_names(tree) == {"Database", "Path", "create_app"}

    def test_import_yields_configured_app(
        self, dev_module_path: Path, captured: dict[str, Any]
    ) -> None:
        """Importing the module builds the app from the given database and attachments paths."""
        _write_dev_app_module(Path(NORMAL_DB), Path(NORMAL_ATT))

        module = _import_generated(dev_module_path)

        assert hasattr(module, "app")
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{NORMAL_DB}"
        assert captured["attachments_path"] == Path(NORMAL_ATT)

    def test_no_attachments_path(self, dev_module_path: Path, captured: dict[str, Any]) -> None:
        """Without an attachments directory no attachments_path argument is generated."""
        _write_dev_app_module(Path(NORMAL_DB), None)

        source = dev_module_path.read_text(encoding="utf-8")
        compile(source, str(dev_module_path), "exec")
        assert "attachments_path" not in source
        assert _called_names(ast.parse(source)) == {"Database", "create_app"}

        _import_generated(dev_module_path)
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{NORMAL_DB}"
        assert captured["attachments_path"] is None

    def test_works_with_real_create_app(
        self,
        dev_module_path: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End to end with the real app factory (no fake) for ordinary paths."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        db_path = tmp_path / "archive.db"
        att_path = tmp_path / "attachments"
        att_path.mkdir()
        _write_dev_app_module(db_path, att_path)

        module = _import_generated(dev_module_path)

        assert module.app.state.database.database_url == f"sqlite+aiosqlite:///{db_path}"
        assert module.app.state.attachments_path == att_path.resolve()


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
        assert _called_names(ast.parse(source)) == {"Database", "Path", "create_app"}

        _import_generated(dev_module_path)

        assert not marker.exists(), "injected code was executed"
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{hostile}"
        assert captured["attachments_path"] == Path(NORMAL_ATT)

    def test_attachments_path(
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
        assert _called_names(ast.parse(source)) == {"Database", "Path", "create_app"}

        _import_generated(dev_module_path)

        assert not marker.exists(), "injected code was executed"
        assert captured["database"].database_url == f"sqlite+aiosqlite:///{NORMAL_DB}"
        assert str(captured["attachments_path"]) == str(hostile)

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
        assert str(captured["attachments_path"]) == str(hostile)
