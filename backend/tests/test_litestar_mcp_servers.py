"""Tests for the MCP server test-connection endpoint (PR-H, Fix 3)."""

from unittest.mock import MagicMock, patch

import httpx
from litestar.testing import create_test_client

from app.database import create_mcp_server as db_create_mcp_server
from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.mcp_servers import mcp_servers_router


def _client():
    return create_test_client(
        route_handlers=[health_router, mcp_servers_router],
        dependencies={"caller": provide_caller},
    )


def test_mcp_server_test_connection_http_reachable(isolated_db):
    """HTTP server: any HTTP response (even 405) means reachable."""
    create_user_role("admin-key-test1", "Admin", "admin")
    sid = db_create_mcp_server(
        name="http-ok",
        server_type="http",
        url="http://localhost:9999",
    )

    fake_resp = MagicMock()
    fake_resp.status_code = 405

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get = MagicMock(return_value=fake_resp)

    with patch("httpx.Client", return_value=fake_client):
        with _client() as c:
            resp = c.post(
                f"/admin/mcp-servers/{sid}/test",
                headers={"X-API-Key": "admin-key-test1"},
            )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    assert "405" in body["message"]


def test_mcp_server_test_connection_http_unreachable(isolated_db):
    """HTTP server: httpx.HTTPError means unreachable."""
    create_user_role("admin-key-test2", "Admin", "admin")
    sid = db_create_mcp_server(
        name="http-down",
        server_type="http",
        url="http://localhost:1",
    )

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get = MagicMock(side_effect=httpx.ConnectError("nope"))

    with patch("httpx.Client", return_value=fake_client):
        with _client() as c:
            resp = c.post(
                f"/admin/mcp-servers/{sid}/test",
                headers={"X-API-Key": "admin-key-test2"},
            )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "Unreachable" in body["message"]


def test_mcp_server_test_connection_stdio_found(isolated_db):
    """stdio server: shutil.which() returns a path → success."""
    create_user_role("admin-key-test3", "Admin", "admin")
    sid = db_create_mcp_server(
        name="stdio-ok",
        server_type="stdio",
        command="foo",
    )

    with patch("app.services.mcp_sync_service.shutil.which", return_value="/usr/bin/foo"):
        with _client() as c:
            resp = c.post(
                f"/admin/mcp-servers/{sid}/test",
                headers={"X-API-Key": "admin-key-test3"},
            )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    assert "foo" in body["message"]


def test_mcp_server_test_connection_stdio_missing(isolated_db):
    """stdio server: shutil.which() returns None → failure."""
    create_user_role("admin-key-test4", "Admin", "admin")
    sid = db_create_mcp_server(
        name="stdio-missing",
        server_type="stdio",
        command="nosuchbinary",
    )

    with patch("app.services.mcp_sync_service.shutil.which", return_value=None):
        with _client() as c:
            resp = c.post(
                f"/admin/mcp-servers/{sid}/test",
                headers={"X-API-Key": "admin-key-test4"},
            )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "not found" in body["message"]


def test_mcp_server_test_connection_unknown_type(isolated_db):
    """Unknown server_type returns success=False with explanatory message."""
    create_user_role("admin-key-test5", "Admin", "admin")
    sid = db_create_mcp_server(
        name="custom-srv",
        server_type="custom",
    )

    with _client() as c:
        resp = c.post(
            f"/admin/mcp-servers/{sid}/test",
            headers={"X-API-Key": "admin-key-test5"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "custom" in body["message"]


def test_mcp_server_test_connection_server_not_found(isolated_db):
    """Non-existent server_id returns 404."""
    create_user_role("admin-key-test6", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/mcp-servers/missing-id/test",
            headers={"X-API-Key": "admin-key-test6"},
        )
    assert resp.status_code == 404
