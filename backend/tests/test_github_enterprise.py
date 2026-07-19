"""GitHub Enterprise (github_host) support regressions.

A project added with a GHE URL (https://github.acme.com/org/repo) must use
that host for ALL git/GitHub work: clone, validation, gh CLI calls, update
routes, discovery import, monitor polling, and PR-diff fetching.
"""

import subprocess
from types import SimpleNamespace

import pytest
from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app.services.github_monitor_service import GitHubMonitorService
from app.services.github_service import GitHubService
from app_litestar.auth import provide_caller
from app_litestar.routes.projects import projects_router

GHE = "ghe.acme.com"


# ---------------------------------------------------------------------------
# GitHubService seam
# ---------------------------------------------------------------------------


def test_parse_repo_url_with_host():
    assert GitHubService.parse_repo_url_with_host("https://github.com/o/r") == (
        "o",
        "r",
        "github.com",
    )
    assert GitHubService.parse_repo_url_with_host(f"https://{GHE}/org/repo.git") == (
        "org",
        "repo",
        GHE,
    )
    # ssh forms (GHE repo pages default to the SSH clone URL)
    assert GitHubService.parse_repo_url_with_host(f"git@{GHE}:org/repo.git") == (
        "org",
        "repo",
        GHE,
    )
    assert GitHubService.parse_repo_url_with_host(f"ssh://git@{GHE}/org/repo") == (
        "org",
        "repo",
        GHE,
    )
    # www.github.com is dotcom, not an enterprise host
    assert GitHubService.parse_repo_url_with_host("https://www.github.com/o/r")[2] == "github.com"
    # back-compat 2-tuple wrapper
    assert GitHubService.parse_repo_url(f"https://{GHE}/org/repo") == ("org", "repo")
    with pytest.raises(ValueError):
        GitHubService.parse_repo_url_with_host("not a url")


def test_api_base_for_host():
    assert GitHubService.api_base_for_host("github.com") == "https://api.github.com"
    assert GitHubService.api_base_for_host(GHE) == f"https://{GHE}/api/v3"
    # GHE Cloud data residency uses api.HOST, not HOST/api/v3
    assert GitHubService.api_base_for_host("acme.ghe.com") == "https://api.acme.ghe.com"


def test_gh_env_only_set_for_enterprise_hosts():
    assert GitHubService._gh_env(None) is None
    assert GitHubService._gh_env("github.com") is None
    env = GitHubService._gh_env(GHE)
    assert env["GH_HOST"] == GHE


def test_origin_host_parses_https_and_ssh(monkeypatch):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=fake_run.remote + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    fake_run.remote = f"https://{GHE}/org/repo.git"
    assert GitHubService._origin_host("/tmp/x") == GHE
    fake_run.remote = f"git@{GHE}:org/repo.git"
    assert GitHubService._origin_host("/tmp/x") == GHE


def test_clone_repo_keeps_enterprise_host(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    GitHubService.clone_repo(f"https://{GHE}/org/repo", target_dir=str(tmp_path / "c"))
    cmd, env = calls[0]
    assert f"https://{GHE}/org/repo.git" in cmd
    assert env["GH_HOST"] == GHE


def test_validate_repo_url_never_probes_user_supplied_hosts(monkeypatch):
    """SSRF guard: a pasted non-github.com host must not be contacted from the
    backend process (no gh subprocess with GH_HOST, no httpx probe)."""

    def boom(*args, **kwargs):
        raise AssertionError("must not probe a user-supplied host")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr("httpx.get", boom)
    assert GitHubService.validate_repo_url(f"https://{GHE}/org/repo") is True
    assert GitHubService.validate_repo_url("https://10.0.0.5:8443/a/b") is True  # never probed
    assert GitHubService.validate_repo_url("not a url") is False


def test_validate_repo_url_still_probes_dotcom(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=1, stdout="", stderr="")  # force httpx fallback

    def fake_get(url, **kwargs):
        seen["url"] = url
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("httpx.get", fake_get)
    assert GitHubService.validate_repo_url("https://github.com/org/repo") is True
    assert seen["url"] == "https://api.github.com/repos/org/repo"


def test_push_branch_targets_origin_hostname(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(GitHubService, "_origin_host", staticmethod(lambda p: GHE))
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert GitHubService.push_branch("/tmp/x", "b1") is True
    auth_cmd, auth_env = calls[0]
    assert auth_cmd[:3] == ["gh", "auth", "setup-git"]
    assert "--hostname" in auth_cmd and GHE in auth_cmd
    assert auth_env["GH_HOST"] == GHE


def test_create_pull_request_pins_origin_host(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env")))
        return SimpleNamespace(returncode=0, stdout=f"https://{GHE}/org/repo/pull/1\n", stderr="")

    monkeypatch.setattr(GitHubService, "_origin_host", staticmethod(lambda p: GHE))
    monkeypatch.setattr(subprocess, "run", fake_run)
    url = GitHubService.create_pull_request("/tmp/x", "b1", "t", "b")
    assert url == f"https://{GHE}/org/repo/pull/1"
    assert calls[0][1]["GH_HOST"] == GHE


# ---------------------------------------------------------------------------
# Project routes (update parity with create)
# ---------------------------------------------------------------------------


def _client():
    return create_test_client(
        route_handlers=[projects_router],
        dependencies={"caller": provide_caller},
    )


def _auth(key="admin-key-ghe"):
    create_user_role(key, "Admin", "admin")
    return {"X-API-Key": key}


def test_update_project_extracts_host_from_pasted_url(isolated_db):
    headers = _auth()
    with _client() as c:
        pid = c.post("/admin/projects/", headers=headers, json={"name": "P"}).json()["project"][
            "id"
        ]
        c.put(
            f"/admin/projects/{pid}",
            headers=headers,
            json={"github_repo": f"https://{GHE}/org/repo.git"},
        )
        project = c.get(f"/admin/projects/{pid}", headers=headers).json()
    assert project["github_repo"] == "org/repo"
    assert project["github_host"] == GHE


def test_update_project_accepts_scp_style_ssh_url(isolated_db):
    headers = _auth("admin-key-ghe-ssh")
    with _client() as c:
        pid = c.post("/admin/projects/", headers=headers, json={"name": "P3"}).json()["project"][
            "id"
        ]
        c.put(
            f"/admin/projects/{pid}",
            headers=headers,
            json={"github_repo": f"git@{GHE}:org/repo.git"},
        )
        project = c.get(f"/admin/projects/{pid}", headers=headers).json()
    assert project["github_repo"] == "org/repo"
    assert project["github_host"] == GHE


def test_update_project_bare_slug_keeps_stored_host(isolated_db):
    headers = _auth("admin-key-ghe2")
    with _client() as c:
        pid = c.post("/admin/projects/", headers=headers, json={"name": "P2"}).json()["project"][
            "id"
        ]
        c.put(
            f"/admin/projects/{pid}",
            headers=headers,
            json={"github_repo": f"https://{GHE}/org/repo"},
        )
        # editing to a bare slug must NOT silently reset the host to github.com
        c.put(f"/admin/projects/{pid}", headers=headers, json={"github_repo": "org/other"})
        project = c.get(f"/admin/projects/{pid}", headers=headers).json()
    assert project["github_repo"] == "org/other"
    assert project["github_host"] == GHE


# ---------------------------------------------------------------------------
# Discovery import
# ---------------------------------------------------------------------------


def test_import_repos_stores_ghe_host(isolated_db, tmp_path):
    from app.database import get_project
    from app.services.project_discovery_service import ProjectDiscoveryService

    result = ProjectDiscoveryService.import_repos(
        [
            {
                "name": "ghe-proj",
                "local_path": str(tmp_path),
                "remote_url": f"git@{GHE}:org/repo.git",
            }
        ]
    )
    assert result["imported"], result
    project = get_project(result["imported"][0]["project_id"])
    assert project["github_repo"] == "org/repo"
    assert project["github_host"] == GHE

    # dedup must still recognize the new-style (bare slug + host) row
    again = ProjectDiscoveryService.import_repos(
        [
            {
                "name": "ghe-proj",
                "local_path": str(tmp_path / "elsewhere"),
                "remote_url": f"https://{GHE}/org/repo",
            }
        ]
    )
    assert not again["imported"]
    assert again["skipped"][0]["reason"] == "already imported"


# ---------------------------------------------------------------------------
# Monitor service
# ---------------------------------------------------------------------------


def test_monitor_api_url_uses_ghe_api_v3():
    ghe_source = {"url": f"https://{GHE}/org/repo"}
    assert (
        GitHubMonitorService._api_url(ghe_source)
        == f"https://{GHE}/api/v3/repos/org/repo/releases/latest"
    )
    dotcom = {"url": "https://github.com/org/repo"}
    assert (
        GitHubMonitorService._api_url(dotcom)
        == "https://api.github.com/repos/org/repo/releases/latest"
    )


def test_monitor_auth_headers_never_send_dotcom_pat_to_ghe(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "dotcom-pat")
    monkeypatch.delenv("GH_ENTERPRISE_TOKEN", raising=False)
    assert GitHubMonitorService._auth_headers()["Authorization"] == "Bearer dotcom-pat"
    # no enterprise token configured -> skip, never leak the github.com PAT
    assert GitHubMonitorService._auth_headers(GHE) is None
    monkeypatch.setenv("GH_ENTERPRISE_TOKEN", "ghe-pat")
    assert GitHubMonitorService._auth_headers(GHE)["Authorization"] == "Bearer ghe-pat"


# ---------------------------------------------------------------------------
# Execution runner
# ---------------------------------------------------------------------------


def test_fetch_pr_diff_allows_project_ghe_host(isolated_db, monkeypatch):
    from app.db.projects import create_project as db_create_project
    from app.services.execution_runner import fetch_pr_diff

    db_create_project(name="G", github_repo="org/repo", github_host=GHE)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b"diff --git a b"

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: FakeResponse())
    assert fetch_pr_diff({"pr_url": f"https://{GHE}/org/repo/pull/1"}) == "diff --git a b"
    # a host configured on no project row stays refused (SSRF guard intact)
    assert fetch_pr_diff({"pr_url": "https://evil.example.com/org/repo/pull/1"}) is None


def test_clone_repos_resolves_project_placeholder(monkeypatch):
    import app.services.execution_runner as runner
    from app.services.project_workspace_service import ProjectWorkspaceService

    monkeypatch.setattr(
        ProjectWorkspaceService, "resolve_working_directory", staticmethod(lambda pid: "/ws/proj")
    )
    cloned_dirs, repo_map = [], {}
    paths = runner.clone_repos(
        [{"path_type": "project", "local_project_path": "project://proj-abc123"}],
        cloned_dirs,
        repo_map,
    )
    assert paths == ["/ws/proj"]
    # The persistent workspace must NEVER enter the temp-clone bookkeeping:
    # cloned_dirs entries get deleted after the run, and github_repo_map
    # drives the auto-resolve PR flow (branch-switch + sweep-commit + push).
    assert cloned_dirs == []
    assert repo_map == {}


def test_derive_run_github_hosts_and_pin(monkeypatch):
    from app.services.execution_runner import derive_run_github_hosts, ghe_host_to_pin

    monkeypatch.setattr(
        "app.database.get_project",
        lambda pid: {"id": pid, "github_repo": "org/repo", "github_host": GHE},
    )
    repo_map = {"/tmp/a": "https://github.com/org/a"}
    entries = [{"path_type": "project", "local_project_path": "project://proj-x"}]
    hosts = derive_run_github_hosts(repo_map, entries)
    assert hosts == {"github.com", GHE}

    # Mixed run: pinning GH_HOST would break gh inside the github.com clone.
    assert ghe_host_to_pin(hosts) is None
    # Pure GHE run: pin.
    assert ghe_host_to_pin({GHE}) == GHE
    # Pure dotcom run: nothing to pin.
    assert ghe_host_to_pin({"github.com"}) is None
    assert ghe_host_to_pin(set()) is None


def test_egress_allowlist_unions_run_hosts(monkeypatch):
    from app.services.execution_service import ExecutionService

    monkeypatch.delenv("AGENTED_EGRESS_ALLOWLIST", raising=False)
    assert GHE in ExecutionService._egress_allowlist_from_env({GHE})
    assert "github.com" in ExecutionService._egress_allowlist_from_env({GHE})
    # explicit operator allowlist still gains the run's GHE host
    monkeypatch.setenv("AGENTED_EGRESS_ALLOWLIST", "example.com")
    assert ExecutionService._egress_allowlist_from_env({GHE}) == {"example.com", GHE}


def test_poll_source_sends_ghe_token_to_ghe_api(isolated_db, monkeypatch):
    """End-to-end seam: a GHE source polls HOST/api/v3 with the enterprise
    token — the github.com PAT must never reach the enterprise host."""
    import httpx

    monkeypatch.setenv("GITHUB_TOKEN", "dotcom-pat")
    monkeypatch.setenv("GH_ENTERPRISE_TOKEN", "ghe-pat")
    seen = {}

    def fake_get(url, headers=None, **kwargs):
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        return SimpleNamespace(status_code=304, headers={}, content=b"")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = GitHubMonitorService.poll_source({"id": "src-1", "url": f"https://{GHE}/org/repo"})
    assert result == {"changed": False}
    assert seen["url"] == f"https://{GHE}/api/v3/repos/org/repo/releases/latest"
    assert seen["auth"] == "Bearer ghe-pat"
