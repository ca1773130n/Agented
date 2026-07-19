"""Per-host GitHub token storage (vault-backed) regressions.

Covers GithubCredentialsService CRUD/resolution, the git/gh call-site wiring
(clone credential helper, gh env, harness pin env, monitor headers), and the
/admin/github-credentials routes.
"""

import subprocess
from types import SimpleNamespace

import pytest
from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app.services.github_credentials_service import (
    GithubCredentialsService,
    env_token_var,
    gh_env_token_var,
    is_dotcom_class,
)
from app.services.github_monitor_service import GitHubMonitorService
from app.services.github_service import GitHubService
from app.services.project_workspace_service import ProjectWorkspaceService
from app_litestar.routes.admin_tooling import github_credentials_router

GHE = "ghe.acme.com"


@pytest.fixture
def vault(isolated_db, monkeypatch):
    """Configure the secrets vault with a fresh Fernet key."""
    from cryptography.fernet import Fernet

    from app.services.secret_vault_service import SecretVaultService

    monkeypatch.setenv("AGENTED_VAULT_KEYS", Fernet.generate_key().decode())
    SecretVaultService.reset()
    yield
    SecretVaultService.reset()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def test_host_classification():
    assert is_dotcom_class("github.com")
    assert is_dotcom_class("acme.ghe.com")
    assert not is_dotcom_class(GHE)
    assert env_token_var(GHE) == "GH_ENTERPRISE_TOKEN"
    assert env_token_var("github.com") == "GITHUB_TOKEN"
    assert gh_env_token_var("github.com") == "GH_TOKEN"
    assert gh_env_token_var(GHE) == "GH_ENTERPRISE_TOKEN"


def test_set_get_delete_roundtrip(vault):
    meta = GithubCredentialsService.set_token(GHE, "tok-1")
    assert meta["host"] == GHE
    assert GithubCredentialsService.stored_token_for_host(GHE) == "tok-1"
    # rotate in place — still one row
    GithubCredentialsService.set_token(GHE, "tok-2")
    assert GithubCredentialsService.stored_token_for_host(GHE) == "tok-2"
    assert [h["host"] for h in GithubCredentialsService.list_hosts()] == [GHE]
    assert GithubCredentialsService.delete_token(GHE) is True
    assert GithubCredentialsService.stored_token_for_host(GHE) is None
    assert GithubCredentialsService.delete_token(GHE) is False


def test_set_token_rejects_garbage_host(vault):
    with pytest.raises(ValueError):
        GithubCredentialsService.set_token("https://ghe.acme.com/x", "tok")
    with pytest.raises(ValueError):
        GithubCredentialsService.set_token("git@host:org", "tok")


def test_token_for_host_stored_wins_env_falls_back(vault, monkeypatch):
    monkeypatch.setenv("GH_ENTERPRISE_TOKEN", "env-tok")
    assert GithubCredentialsService.token_for_host(GHE) == "env-tok"
    GithubCredentialsService.set_token(GHE, "stored-tok")
    assert GithubCredentialsService.token_for_host(GHE) == "stored-tok"
    # dotcom class never reads the enterprise var
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert GithubCredentialsService.token_for_host("github.com") is None


def test_unconfigured_vault_is_env_only(isolated_db, monkeypatch):
    monkeypatch.delenv("AGENTED_VAULT_KEYS", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "env-dotcom")
    assert GithubCredentialsService.stored_token_for_host("github.com") is None
    assert GithubCredentialsService.token_for_host("github.com") == "env-dotcom"


# ---------------------------------------------------------------------------
# gh / git call-site wiring
# ---------------------------------------------------------------------------


def test_gh_env_includes_stored_token(vault):
    GithubCredentialsService.set_token(GHE, "ghe-tok")
    env = GitHubService._gh_env(GHE)
    assert env["GH_HOST"] == GHE
    assert env["GH_ENTERPRISE_TOKEN"] == "ghe-tok"
    # dotcom with stored token: no GH_HOST, but GH_TOKEN set
    GithubCredentialsService.set_token("github.com", "dotcom-tok")
    env = GitHubService._gh_env("github.com")
    assert "GH_HOST" not in env or env.get("GH_HOST") != "github.com"
    assert env["GH_TOKEN"] == "dotcom-tok"


def test_gh_env_unchanged_without_stored_token(vault):
    assert GitHubService._gh_env("github.com") is None
    assert GitHubService._gh_env(None) is None
    env = GitHubService._gh_env(GHE)
    assert env["GH_HOST"] == GHE
    assert "GH_ENTERPRISE_TOKEN" not in {k: v for k, v in env.items() if v == ""}


def test_workspace_clone_uses_credential_helper(vault, monkeypatch):
    GithubCredentialsService.set_token(GHE, "clone-tok")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    project = {"github_host": GHE, "github_repo": "org/repo"}
    args, env = ProjectWorkspaceService._git_auth(project)
    assert env["AGENTED_GIT_TOKEN"] == "clone-tok"
    assert "clone-tok" not in " ".join(args)  # token never in argv
    assert any("credential.helper=!f()" in a for a in args)
    # first -c clears inherited helpers so the stored token wins
    assert args[args.index("-c") + 1] == "credential.helper="


def test_workspace_clone_ambient_without_token(vault):
    args, env = ProjectWorkspaceService._git_auth({"github_host": GHE})
    assert args == [] and env is None


def test_gh_pin_env_additions(vault):
    from app.services.execution_runner import gh_pin_env_additions

    assert gh_pin_env_additions(GHE) == {"GH_HOST": GHE}
    GithubCredentialsService.set_token(GHE, "pin-tok")
    assert gh_pin_env_additions(GHE) == {"GH_HOST": GHE, "GH_ENTERPRISE_TOKEN": "pin-tok"}


def test_monitor_prefers_stored_token(vault, monkeypatch):
    monkeypatch.setenv("GH_ENTERPRISE_TOKEN", "env-tok")
    GithubCredentialsService.set_token(GHE, "stored-tok")
    headers = GitHubMonitorService._auth_headers(GHE)
    assert headers["Authorization"] == "Bearer stored-tok"
    GithubCredentialsService.delete_token(GHE)
    assert GitHubMonitorService._auth_headers(GHE)["Authorization"] == "Bearer env-tok"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _client():
    # The router is admin-gated; the guard reads the principal that
    # ApiKeyMiddleware resolves, so the test client needs the middleware.
    from app_litestar.middleware import ApiKeyMiddleware

    return create_test_client(
        route_handlers=[github_credentials_router], middleware=[ApiKeyMiddleware()]
    )


def _admin(email="ghc-admin@test"):
    from app.database import get_connection
    from app.db.rbac import generate_api_key

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (email, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    assert create_user_role(api_key, label="t", role="admin", user_id=email) is not None
    return {"X-API-Key": api_key}


def test_credentials_routes_crud(vault):
    headers = _admin("ghc-admin-crud@test")
    with _client() as c:
        assert c.get("/admin/github-credentials/", headers=headers).json() == {"hosts": []}
        resp = c.put(f"/admin/github-credentials/{GHE}", headers=headers, json={"token": "tok-x"})
        assert resp.status_code == 200
        assert resp.json()["host"] == GHE
        assert "tok-x" not in resp.text  # token never echoed back
        hosts = c.get("/admin/github-credentials/", headers=headers).json()["hosts"]
        assert [h["host"] for h in hosts] == [GHE]
        assert c.delete(f"/admin/github-credentials/{GHE}", headers=headers).status_code == 200
        assert c.delete(f"/admin/github-credentials/{GHE}", headers=headers).status_code == 404


def test_credentials_routes_reject_bad_input(vault):
    headers = _admin("ghc-admin-bad@test")
    with _client() as c:
        assert (
            c.put(f"/admin/github-credentials/{GHE}", headers=headers, json={}).status_code == 400
        )
        assert (
            c.put(
                "/admin/github-credentials/not a host!", headers=headers, json={"token": "t"}
            ).status_code
            == 400
        )


def test_credentials_routes_503_without_vault(isolated_db, monkeypatch):
    monkeypatch.delenv("AGENTED_VAULT_KEYS", raising=False)
    headers = _admin("ghc-admin-503@test")
    with _client() as c:
        assert c.get("/admin/github-credentials/", headers=headers).status_code == 503
