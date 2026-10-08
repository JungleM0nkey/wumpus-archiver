"""How ``serve --build-portal`` and ``dev`` prepare to start.

They install the portal's dependencies only when ``node_modules`` is missing or older
than the portal's lockfile, and both check settings before starting anything. npm and
the dev processes are faked: nothing here runs npm or uvicorn.
"""

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from wumpus_archiver import cli as cli_module
from wumpus_archiver.cli import _build_portal_static, _ensure_portal_dependencies, cli

INSTALLED_AT = 1_700_000_000  # the time npm last wrote its record of the tree


def _portal(
    root: Path,
    *,
    lockfile_at: int | None = INSTALLED_AT - 60,
    node_modules: bool = True,
    record: bool = True,
) -> Path:
    """A portal dir with an optional lockfile and an optional installed tree.

    ``lockfile_at`` is the lockfile's modification time; ``None`` means no lockfile.
    By default the lockfile predates the install, so the tree is current.
    """
    portal = root / "portal"
    portal.mkdir()
    if lockfile_at is not None:
        lockfile = portal / "package-lock.json"
        lockfile.write_text('{"lockfileVersion": 3, "packages": {}}')
        os.utime(lockfile, (lockfile_at, lockfile_at))
    if node_modules:
        (portal / "node_modules").mkdir()
        if record:
            installed = portal / "node_modules" / ".package-lock.json"
            installed.write_text('{"lockfileVersion": 3, "packages": {}}')
            os.utime(installed, (INSTALLED_AT, INSTALLED_AT))
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
    def test_an_install_newer_than_the_lockfile_is_left_alone(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        _ensure_portal_dependencies("npm", _portal(tmp_path))
        assert npm.commands == []

    def test_a_lockfile_changed_since_the_install_rebuilds_the_tree(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        """A pull, merge or branch switch that changes the lockfile makes it newer."""
        _ensure_portal_dependencies("npm", _portal(tmp_path, lockfile_at=INSTALLED_AT + 1))
        assert npm.commands == [["ci"]]

    def test_a_fresh_checkout_installs_from_the_lockfile(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        _ensure_portal_dependencies("npm", _portal(tmp_path, node_modules=False))
        assert npm.commands == [["ci"]]

    def test_a_tree_without_an_npm_record_is_left_alone(self, tmp_path: Path, npm: FakeNpm) -> None:
        """Another package manager's tree (or package-lock=false) is never wiped."""
        _ensure_portal_dependencies("npm", _portal(tmp_path, record=False))
        assert npm.commands == []

    def test_without_a_lockfile_an_existing_install_is_kept(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        _ensure_portal_dependencies("npm", _portal(tmp_path, lockfile_at=None))
        assert npm.commands == []

    def test_without_a_lockfile_a_fresh_checkout_installs(
        self, tmp_path: Path, npm: FakeNpm
    ) -> None:
        _ensure_portal_dependencies("npm", _portal(tmp_path, lockfile_at=None, node_modules=False))
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
        portal = _portal(tmp_path, lockfile_at=INSTALLED_AT + 1)
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
        lockfile = dev_env["portal"] / "package-lock.json"
        os.utime(lockfile, (INSTALLED_AT + 1, INSTALLED_AT + 1))
        result = CliRunner().invoke(cli, ["dev", str(dev_env["db"])])
        assert result.exit_code == 0, result.output
        assert dev_env["npm"].commands == [["ci"]]
        assert dev_env["started"] == [["backend", "frontend"]]


class TestUnreadableDotEnv:
    """A ``.env`` that cannot be decoded is a settings error, not a traceback."""

    @pytest.fixture
    def latin1_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_bytes("PORTAL_TITLE=Caf\xe9\n".encode("latin-1"))
        db_file = tmp_path / "archive.db"
        db_file.touch()
        return db_file

    def test_dev_reports_it(self, dev_env: dict[str, Any], latin1_env: Path) -> None:
        result = CliRunner().invoke(cli, ["dev", str(latin1_env)])
        assert result.exit_code == 1
        assert "Failed to load settings" in result.output
        assert dev_env["started"] == []

    def test_serve_reports_it(self, latin1_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("uvicorn.run", lambda app, **kw: pytest.fail("uvicorn must not run"))
        result = CliRunner().invoke(cli, ["serve", str(latin1_env)])
        assert result.exit_code == 1
        assert "Failed to load settings" in result.output
