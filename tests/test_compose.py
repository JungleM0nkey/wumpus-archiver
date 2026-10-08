"""The composition helpers that ``serve`` and the dev module share."""

from pathlib import Path

import pytest

from wumpus_archiver import compose


def _build(root: Path) -> Path:
    """A built portal under ``root``: ``portal/build/index.html`` and nothing else."""
    build = root / "portal" / "build"
    build.mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html>")
    return build


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty fake checkout for the source-tree lookup and an empty working directory."""
    fake_module = tmp_path / "checkout" / "src" / "wumpus_archiver" / "compose.py"
    monkeypatch.setattr(compose, "__file__", str(fake_module))
    (tmp_path / "cwd").mkdir()
    monkeypatch.chdir(tmp_path / "cwd")
    return tmp_path


class TestPortalBuildDir:
    def test_a_build_without_the_portal_sources_is_served(self, roots: Path) -> None:
        """A deployment that ships only ``portal/build`` (no package.json) still gets the UI."""
        build = _build(roots / "cwd")
        assert not (build.parent / "package.json").exists()
        found = compose.portal_build_dir()
        assert found is not None and found.resolve() == build.resolve()

    def test_the_source_tree_build_comes_first(self, roots: Path) -> None:
        source = _build(roots / "checkout")
        _build(roots / "cwd")
        found = compose.portal_build_dir()
        assert found is not None and found.resolve() == source.resolve()

    def test_none_without_a_built_index(self, roots: Path) -> None:
        (roots / "cwd" / "portal" / "build").mkdir(parents=True)
        assert compose.portal_build_dir() is None
