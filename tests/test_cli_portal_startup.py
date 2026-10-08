"""How ``serve --build-portal`` and ``dev`` prepare to start.

They install the portal's dependencies only when ``node_modules`` does not match the
portal's lockfile, and ``dev`` checks settings before starting anything. npm and the
dev processes are faked: nothing here runs npm or uvicorn.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from wumpus_archiver import cli as cli_module
from wumpus_archiver.cli import _build_portal_static, _ensure_portal_dependencies, cli

# A lockfile in npm's v3 shape: the root entry, two packages and an optional binary
# for another platform, which npm never installs here.
LOCKED: dict[str, dict[str, Any]] = {
    "": {"name": "portal"},
    "node_modules/vite": {"version": "8.3.3", "dev": True},
    "node_modules/cookie": {"version": "2.0.1"},
    "node_modules/@rolldown/binding-win32-x64-msvc": {"version": "1.0.0", "optional": True},
}
INSTALLED = {
    "node_modules/vite": {"version": "8.3.3", "dev": True},
    "node_modules/cookie": {"version": "2.0.1"},
}


def _portal(
    root: Path,
    *,
    locked: dict[str, dict[str, Any]] | None = LOCKED,
    installed: dict[str, dict[str, Any]] | None = INSTALLED,
    node_modules: bool = True,
) -> Path:
    """A portal dir with an optional lockfile and an optional installed tree."""
    portal = root / "portal"
    portal.mkdir()
    if locked is not None:
        (portal / "package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": locked})
        )
    if node_modules:
        (portal / "node_modules").mkdir()
        if installed is not None:
            (portal / "node_modules" / ".package-lock.json").write_text(
                json.dumps({"lockfileVersion": 3, "packages": installed})
            )
    return portal


class FakeNpm:
    """Records every npm command; fails the ones named in ``failing``."""

    def __init__(self, failing: tuple[str, ...] = ()) -> None:
        self.commands: list[list[str]] = []
        self.failing = failing

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(command[1:])
        failed = command[1] in self.failing
        return subprocess.CompletedProcess(
            command, 1 if failed else 0, stdout="", stderr="npm ERR! boom" if failed else ""
        )


@pytest.fixture
def npm(monkeypatch: pytest.MonkeyPatch) -> FakeNpm:
    fake = FakeNpm()
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


class TestEnsurePortalDependencies:
    def test_an_install_matching_the_lockfile_is_left_alone(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        """Optional packages for other platforms are never installed and not required."""
        _ensure_portal_dependencies("npm", _portal(tmp_path))
        assert npm.commands == []

    @pytest.mark.parametrize(
        "portal_kwargs",
        [
            pytest.param({"node_modules": False}, id="no-node-modules"),
            pytest.param({"installed": None}, id="no-installed-record"),
            pytest.param(
                {"installed": {**INSTALLED, "node_modules/vite": {"version": "7.3.5"}}},
                id="older-version-installed",
            ),
            pytest.param(
                {"installed": {"node_modules/vite": {"version": "8.3.3"}}},
                id="locked-package-missing",
            ),
            pytest.param(
                {"installed": {**INSTALLED, "node_modules/esbuild": {"version": "0.28.1"}}},
                id="package-no-longer-locked",
            ),
        ],
    )
    def test_a_stale_install_is_redone_from_the_lockfile(
        self, tmp_path: Path, npm: FakeNpm, portal_kwargs: dict[str, Any]
    ) -> None:
        _ensure_portal_dependencies("npm", _portal(tmp_path, **portal_kwargs))
        assert npm.commands == [["ci"]]

    def test_an_unreadable_installed_record_counts_as_stale(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        portal = _portal(tmp_path)
        (portal / "node_modules" / ".package-lock.json").write_text("{not json")
        _ensure_portal_dependencies("npm", portal)
        assert npm.commands == [["ci"]]

    def test_without_a_lockfile_an_existing_install_is_kept(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        _ensure_portal_dependencies("npm", _portal(tmp_path, locked=None, installed=None))
        assert npm.commands == []

    def test_without_a_lockfile_a_fresh_checkout_installs(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        _ensure_portal_dependencies("npm", _portal(tmp_path, locked=None, node_modules=False))
        assert npm.commands == [["install"]]

    def test_an_install_failure_exits_with_npms_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(subprocess, "run", FakeNpm(failing=("ci",)))
        with pytest.raises(SystemExit) as exited:
            _ensure_portal_dependencies("npm", _portal(tmp_path, node_modules=False))
        assert exited.value.code == 1
        assert "npm ERR! boom" in capsys.readouterr().err


class TestBuildPortal:
    def test_a_stale_install_is_redone_before_the_build(
        self, tmp_path: Path, npm: FakeNpm, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        portal = _portal(tmp_path, installed={"node_modules/vite": {"version": "7.3.5"}})
        monkeypatch.setattr("wumpus_archiver.utils.process_manager.find_npm", lambda: "npm")
        monkeypatch.setattr(
            "wumpus_archiver.utils.process_manager.resolve_portal_dir", lambda: portal
        )
        _build_portal_static()
        assert npm.commands == [["ci"], ["run", "build"]]


@pytest.fixture
def dev_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, npm: FakeNpm) -> dict[str, Any]:
    """``dev`` with a current portal install, no real processes and a clean environment."""
    for var in ("DISCORD_BOT_TOKEN", "API_AUTH_TOKEN", "CORS_ORIGINS", "LOG_LEVEL", "API_PORT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    portal = _portal(tmp_path)
    state: dict[str, Any] = {"portal": portal, "npm": npm, "started": [], "written": []}

    async def fake_run(processes: list[Any], **kwargs: Any) -> int:
        state["started"].append([process.label for process in processes])
        return 0

    monkeypatch.setattr("wumpus_archiver.utils.process_manager.find_npm", lambda: "npm")
    monkeypatch.setattr("wumpus_archiver.utils.process_manager.resolve_portal_dir", lambda: portal)
    monkeypatch.setattr("wumpus_archiver.utils.process_manager.run_concurrently", fake_run)
    monkeypatch.setattr(
        cli_module, "_write_dev_app_module", lambda db, att: state["written"].append(db)
    )
    db_file = tmp_path / "archive.db"
    db_file.touch()
    state["db"] = db_file
    return state


class TestDevStartup:
    @pytest.mark.parametrize(
        ("var", "value"),
        [("LOG_LEVEL", "bogus"), ("CORS_ORIGINS", '["https://a.example"'), ("API_PORT", "70000")],
    )
    def test_invalid_settings_stop_dev_before_anything_starts(
        self, dev_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch, var: str, value: str
    ) -> None:
        monkeypatch.setenv(var, value)
        result = CliRunner().invoke(cli, ["dev", str(dev_env["db"])])
        assert result.exit_code == 1
        assert "Failed to load settings" in result.output
        assert dev_env["started"] == []
        assert dev_env["written"] == []
        assert dev_env["npm"].commands == []

    @pytest.mark.parametrize("token", [None, "", "   "])
    def test_a_missing_or_blank_bot_token_still_starts(
        self, dev_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch, token: str | None
    ) -> None:
        if token is not None:
            monkeypatch.setenv("DISCORD_BOT_TOKEN", token)
        result = CliRunner().invoke(cli, ["dev", str(dev_env["db"])])
        assert result.exit_code == 0, result.output
        assert dev_env["started"] == [["backend", "frontend"]]

    def test_a_stale_install_is_redone_before_dev_starts(self, dev_env: dict[str, Any]) -> None:
        (dev_env["portal"] / "node_modules" / ".package-lock.json").unlink()
        result = CliRunner().invoke(cli, ["dev", str(dev_env["db"])])
        assert result.exit_code == 0, result.output
        assert dev_env["npm"].commands == [["ci"]]
        assert dev_env["started"] == [["backend", "frontend"]]
