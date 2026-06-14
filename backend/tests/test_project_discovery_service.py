"""Tests for ProjectDiscoveryService: filesystem scan, dedup, import."""

import os
import subprocess

from app.services import project_discovery_service as pds


def _make_repo(root: str, name: str) -> str:
    """Create a directory with a .git marker so it scans as a repo."""
    path = os.path.join(root, name)
    os.makedirs(os.path.join(path, ".git"), exist_ok=True)
    return path


def test_scan_fs_finds_immediate_child_repos(tmp_path):
    root = str(tmp_path)
    _make_repo(root, "alpha")
    _make_repo(root, "beta")
    os.makedirs(os.path.join(root, "notes"))  # no .git -> skipped

    repos, unreadable = pds._scan_fs(root, nested=False, max_depth=3)

    names = sorted(r["name"] for r in repos)
    assert names == ["alpha", "beta"]
    assert unreadable == 0
    assert all(r["local_path"].startswith(root) for r in repos)


def test_scan_fs_nested_finds_deep_repos_and_skips_ignored(tmp_path):
    root = str(tmp_path)
    _make_repo(root, "top")
    _make_repo(os.path.join(root, "sub"), "deep")
    _make_repo(os.path.join(root, "node_modules"), "vendored")  # ignored dir

    immediate, _ = pds._scan_fs(root, nested=False, max_depth=3)
    nested, _ = pds._scan_fs(root, nested=True, max_depth=3)

    assert sorted(r["name"] for r in immediate) == ["top"]
    found = sorted(r["name"] for r in nested)
    assert "top" in found and "deep" in found
    assert "vendored" not in found  # node_modules pruned


def test_scan_fs_does_not_descend_into_a_found_repo(tmp_path):
    root = str(tmp_path)
    outer = _make_repo(root, "outer")
    _make_repo(outer, "inner")  # inner repo nested inside a repo

    nested, _ = pds._scan_fs(root, nested=True, max_depth=5)

    names = [r["name"] for r in nested]
    assert names == ["outer"]  # stops at outer, never reaches inner


def test_short_remote_normalizes_forms():
    assert pds._short_remote("git@github.com:org/repo.git") == "github.com/org/repo"
    assert pds._short_remote("https://github.com/org/repo") == "github.com/org/repo"
    assert pds._short_remote("https://github.com/org/repo.git") == "github.com/org/repo"
    assert pds._short_remote("ssh://git@gitlab.com/org/repo.git") == "gitlab.com/org/repo"
    assert pds._short_remote(None) is None
    assert pds._short_remote("") is None


def test_scan_marks_already_imported_by_path_and_remote(tmp_path, isolated_db):
    from app.database import create_project as db_create_project

    root = str(tmp_path)
    a = _make_repo(root, "alpha")   # will dedup by local_path
    b = _make_repo(root, "beta")    # will dedup by remote
    _make_repo(root, "gamma")       # new

    db_create_project(name="Alpha", local_path=a)
    db_create_project(name="Beta", github_repo="github.com/org/beta")

    # Real git remote so beta resolves to github.com/org/beta
    subprocess.run(["git", "init", "-q"], cwd=b, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:org/beta.git"],
        cwd=b, check=True,
    )

    result = pds.ProjectDiscoveryService.scan(root, nested=False, max_depth=3)

    by_name = {r["name"]: r for r in result["repos"]}
    assert by_name["alpha"]["already_imported"] is True
    assert by_name["beta"]["already_imported"] is True
    assert by_name["gamma"]["already_imported"] is False
    assert result["new_count"] == 1


def test_scan_rejects_missing_root():
    import pytest

    with pytest.raises(ValueError):
        pds.ProjectDiscoveryService.scan("/no/such/folder/xyz", nested=False, max_depth=3)
