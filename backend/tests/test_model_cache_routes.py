"""v0.7.8: /admin/backends/{kind}/models + /refresh + /models/cache tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _setup_admin_user(email: str = "ad@test"):
    """Plant an admin user/role and return its API key."""
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key

    user_id = email
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    role_id = create_user_role(api_key, label="t", role="admin", user_id=user_id)
    assert role_id is not None
    return api_key


def _setup_editor_user(email: str = "ed@test"):
    """Plant an editor user/role and return its API key."""
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key

    user_id = email
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    role_id = create_user_role(api_key, label="t", role="editor", user_id=user_id)
    assert role_id is not None
    return api_key


@pytest.fixture
def client(isolated_db):
    """Test client mounting the model_cache router with ApiKeyMiddleware."""
    from litestar.testing import create_test_client

    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.model_cache import model_cache_router

    with create_test_client(
        route_handlers=[model_cache_router],
        middleware=[ApiKeyMiddleware()],
    ) as c:
        yield c


@pytest.fixture
def mock_discover():
    with patch(
        "app.services.model_cache_service.ModelDiscoveryService._discover_raw"
    ) as m:
        m.return_value = ["gpt-5", "gpt-5.1"]
        yield m


def test_get_models_happy_path(client, mock_discover):
    headers = {"X-API-Key": _setup_admin_user()}
    r = client.get(
        "/admin/backends/codex/models?auth_method=api_key", headers=headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["models"] == ["gpt-5", "gpt-5.1"]
    assert body["backend_kind"] == "codex"
    assert body["auth_method"] == "api_key"
    assert body["fresh"] is True


def test_refresh_models_calls_service_refresh(client, mock_discover):
    headers = {"X-API-Key": _setup_admin_user()}
    with patch(
        "app.services.model_cache_service.refresh",
        return_value={"backend_kind": "codex", "auth_method": "api_key", "fresh": True},
    ) as refresh_mock:
        r = client.post(
            "/admin/backends/codex/models/refresh?auth_method=api_key",
            headers=headers,
        )
    assert r.status_code in (200, 201)
    refresh_mock.assert_called_once_with("codex", "api_key")


def test_list_cache_returns_entries(client, mock_discover):
    headers = {"X-API-Key": _setup_admin_user()}
    # Populate the cache.
    client.get("/admin/backends/codex/models?auth_method=api_key", headers=headers)
    r = client.get("/admin/backends/models/cache", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "entries" in body
    assert len(body["entries"]) == 1
    assert body["entries"][0]["backend_kind"] == "codex"
    assert body["entries"][0]["auth_method"] == "api_key"


def test_non_admin_gets_403(client, mock_discover):
    headers = {"X-API-Key": _setup_editor_user()}
    r = client.get(
        "/admin/backends/codex/models?auth_method=api_key", headers=headers
    )
    assert r.status_code == 403
    r = client.post(
        "/admin/backends/codex/models/refresh?auth_method=api_key", headers=headers
    )
    assert r.status_code == 403
    r = client.get("/admin/backends/models/cache", headers=headers)
    assert r.status_code == 403


def test_unauthenticated_blocked(client, mock_discover):
    r = client.get("/admin/backends/codex/models?auth_method=api_key")
    assert r.status_code in (401, 403)
    r = client.post("/admin/backends/codex/models/refresh?auth_method=api_key")
    assert r.status_code in (401, 403)
    r = client.get("/admin/backends/models/cache")
    assert r.status_code in (401, 403)
