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
    a = _make_repo(root, "alpha")  # will dedup by local_path
    b = _make_repo(root, "beta")  # will dedup by remote
    _make_repo(root, "gamma")  # new

    db_create_project(name="Alpha", local_path=a)
    db_create_project(name="Beta", github_repo="github.com/org/beta")

    # Real git remote so beta resolves to github.com/org/beta
    subprocess.run(["git", "init", "-q"], cwd=b, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:org/beta.git"],
        cwd=b,
        check=True,
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


def test_scan_rejects_path_outside_allowlist(monkeypatch):
    """A path outside the allowlist (e.g. /etc) is rejected BEFORE any fs walk."""
    import pytest

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("_scan_fs ran for an out-of-allowlist path")

    monkeypatch.setattr(pds, "_scan_fs", _boom)

    with pytest.raises(ValueError, match="not allowed"):
        pds.ProjectDiscoveryService.scan("/etc", nested=False, max_depth=3)


def test_scan_accepts_in_allowlist_path_with_mocked_walk(tmp_path, isolated_db, monkeypatch):
    """An in-allowlist path (home/tmp/opt) is accepted; the fs walk is mocked."""
    # tmp_path resolves under the system temp dir, which is in the allowlist.
    monkeypatch.setattr(pds, "_scan_fs", lambda *a, **k: ([], 0))

    result = pds.ProjectDiscoveryService.scan(str(tmp_path), nested=False, max_depth=3)

    assert result["scanned"] == 0
    assert result["found"] == 0
    assert result["unreadable"] == 0


def test_scan_accepts_configured_workspace_root(isolated_db, monkeypatch):
    """A path under the configured workspace_root is allowed even outside the
    static bases, and rejected once that setting is cleared."""
    import pytest

    from app.db.settings import set_setting

    captured = {}

    def _fake_walk(root, *a, **k):
        captured["root"] = root
        return ([], 0)

    monkeypatch.setattr(pds, "_scan_fs", _fake_walk)
    monkeypatch.setattr(pds.os.path, "isdir", lambda _p: True)

    set_setting("workspace_root", "/srv/agented-workspaces")

    pds.ProjectDiscoveryService.scan("/srv/agented-workspaces/team-a", nested=False, max_depth=3)
    assert captured["root"] == "/srv/agented-workspaces/team-a"

    # Without the workspace_root setting the same path is rejected.
    set_setting("workspace_root", "")
    with pytest.raises(ValueError, match="not allowed"):
        pds.ProjectDiscoveryService.scan(
            "/srv/agented-workspaces/team-a", nested=False, max_depth=3
        )


def test_import_repos_creates_projects_and_skips_dupes(tmp_path, isolated_db):
    from app.database import create_project as db_create_project
    from app.database import get_all_projects

    existing_path = str(tmp_path / "already")
    db_create_project(name="Already", local_path=existing_path)

    repos = [
        {
            "name": "fresh",
            "local_path": str(tmp_path / "fresh"),
            "remote_url": "git@github.com:org/fresh.git",
        },
        {"name": "Already", "local_path": existing_path, "remote_url": None},
        {"name": "", "local_path": "", "remote_url": None},  # invalid
    ]

    result = pds.ProjectDiscoveryService.import_repos(repos, run_harness_setup=False)

    assert [i["name"] for i in result["imported"]] == ["fresh"]
    reasons = {s["name"]: s["reason"] for s in result["skipped"]}
    assert reasons["Already"] == "already imported"
    assert "(unknown)" in reasons
    assert result["setup_started"] is False
    # The fresh project is persisted with the normalized remote.
    created = [p for p in get_all_projects() if p["name"] == "fresh"][0]
    assert created["github_repo"] == "github.com/org/fresh"


def test_import_repos_spawns_harness_setup_when_team_given(tmp_path, isolated_db, monkeypatch):
    from app.db.teams import create_team

    team_id = create_team(name="Backend")  # owner_team_id has a FK to teams

    calls = []
    monkeypatch.setattr(
        pds.ProjectDiscoveryService,
        "_spawn_harness_setup",
        classmethod(lambda cls, pid: calls.append(pid)),
    )

    repos = [{"name": "fresh", "local_path": str(tmp_path / "fresh"), "remote_url": None}]
    result = pds.ProjectDiscoveryService.import_repos(
        repos,
        owner_team_id=team_id,
        run_harness_setup=True,
    )

    assert result["setup_started"] is True
    assert calls == [result["imported"][0]["project_id"]]


def test_import_repos_no_setup_without_team(tmp_path, isolated_db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        pds.ProjectDiscoveryService,
        "_spawn_harness_setup",
        classmethod(lambda cls, pid: calls.append(pid)),
    )
    repos = [{"name": "fresh", "local_path": str(tmp_path / "fresh"), "remote_url": None}]
    result = pds.ProjectDiscoveryService.import_repos(
        repos,
        owner_team_id=None,
        run_harness_setup=True,
    )
    assert result["setup_started"] is False
    assert calls == []
