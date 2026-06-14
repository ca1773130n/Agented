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
