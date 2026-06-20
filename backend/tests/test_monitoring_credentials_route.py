"""Route-level test for GET /admin/monitoring/credentials (v0.7.93).

Covers the wiring between the endpoint and CredentialResolver: every
account in ``get_all_accounts_with_health()`` becomes one row in the
response, with the same shape the frontend banner consumes.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_e import monitoring_router


@pytest.fixture
def client():
    with create_test_client(
        route_handlers=[monitoring_router],
        dependencies={"caller": provide_caller},
    ) as c:
        yield c


def _seed_admin():
    create_user_role("admin-cred", "Admin", "admin")


def test_credentials_endpoint_returns_per_account_status(client, isolated_db):
    del isolated_db
    _seed_admin()
    accounts = [
        {
            "id": 1,
            "account_name": "Personal1",
            "backend_type": "claude",
            "config_path": "~/.claude-personal1",
        },
        {
            "id": 2,
            "account_name": "Personal2",
            "backend_type": "claude",
            "config_path": "~/.claude-personal2",
        },
    ]
    statuses = [
        {"status": "ok"},
        {
            "status": "missing",
            "remediation": "CLAUDE_CONFIG_DIR=~/.claude-personal2 claude  # then /login",
            "expected_location": "Claude Code-credentials-d552d744",
        },
    ]
    with (
        patch("app.database.get_all_accounts_with_health", return_value=accounts),
        patch(
            "app.services.provider_usage_client.CredentialResolver.check_credentials",
            side_effect=statuses,
        ),
    ):
        resp = client.get(
            "/admin/monitoring/credentials",
            headers={"X-API-Key": "admin-cred"},
        )
    assert resp.status_code == 200
    rows = resp.json()["accounts"]
    assert len(rows) == 2
    ok_row = next(r for r in rows if r["account_id"] == 1)
    missing_row = next(r for r in rows if r["account_id"] == 2)
    assert ok_row["credential_status"] == "ok"
    assert ok_row["remediation"] is None or ok_row["remediation"] == ""
    assert missing_row["credential_status"] == "missing"
    assert "CLAUDE_CONFIG_DIR" in missing_row["remediation"]
    assert missing_row["expected_location"].startswith("Claude Code-credentials-")
    assert missing_row["backend_type"] == "claude"


def test_credentials_endpoint_handles_account_load_failure(client, isolated_db):
    """When the underlying account list fetch raises, the endpoint
    must still return 200 with an empty accounts array — the banner
    is advisory and shouldn't 5xx and break the dashboard.
    """
    del isolated_db
    _seed_admin()
    with patch(
        "app.database.get_all_accounts_with_health",
        side_effect=RuntimeError("boom"),
    ):
        resp = client.get(
            "/admin/monitoring/credentials",
            headers={"X-API-Key": "admin-cred"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"accounts": []}


def test_credentials_endpoint_includes_unsupported_backends(client, isolated_db):
    """Unknown backend types pass through as ``unsupported`` rather
    than being dropped — the dashboard can render a neutral
    "not monitored" state instead of pretending the account
    doesn't exist.
    """
    del isolated_db
    _seed_admin()
    with patch(
        "app.database.get_all_accounts_with_health",
        return_value=[
            {
                "id": 99,
                "account_name": "Custom",
                "backend_type": "openrouter",
                "config_path": None,
            }
        ],
    ):
        resp = client.get(
            "/admin/monitoring/credentials",
            headers={"X-API-Key": "admin-cred"},
        )
    assert resp.status_code == 200
    rows = resp.json()["accounts"]
    assert len(rows) == 1
    assert rows[0]["credential_status"] == "unsupported"
    assert rows[0]["remediation"] is None


# NOTE on auth: route-level handlers under /admin/monitoring/* do
# NOT take ``caller`` as a dependency — auth is enforced by the
# global ApiKey middleware in ``app_litestar/middleware.py``, which
# create_test_client(route_handlers=...) does not install. The
# middleware path is covered by tests in test_litestar_*; this
# file is scoped to the route's response shape.
