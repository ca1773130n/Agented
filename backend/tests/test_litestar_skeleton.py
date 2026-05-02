"""Smoke tests for the Litestar skeleton (track A, wave 22)."""

import pytest
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app.db.users import create_user
from app_litestar.auth import Caller, provide_caller, require_role
from app_litestar.main import create_app


def test_liveness_returns_200(isolated_db):
    from app_litestar.routes.health import liveness
    with create_test_client(route_handlers=[liveness]) as client:
        resp = client.get("/liveness")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_app_returns_litestar_instance(isolated_db):
    app = create_app()
    from litestar import Litestar
    assert isinstance(app, Litestar)


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


def test_provide_caller_returns_admin_in_bootstrap_mode(isolated_db):
    # Wipe user_roles so count_user_roles() == 0. The legacy user from wave 20
    # is still in the users table, that's fine — bootstrap means no roles.
    from app.db.connection import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM user_roles")
        conn.commit()

    caller = provide_caller(_FakeRequest({}))  # type: ignore[arg-type]
    assert isinstance(caller, Caller)
    assert caller.role == "admin"


def test_provide_caller_rejects_missing_key(isolated_db):
    create_user_role("real-key", "Real", "admin")
    with pytest.raises(NotAuthorizedException):
        provide_caller(_FakeRequest({}))  # type: ignore[arg-type]


def test_provide_caller_rejects_unknown_key(isolated_db):
    create_user_role("real-key", "Real", "admin")
    with pytest.raises(NotAuthorizedException):
        provide_caller(_FakeRequest({"X-API-Key": "ghost"}))  # type: ignore[arg-type]


def test_provide_caller_resolves_user_id(isolated_db):
    uid = create_user("ls@example.com", "LS")
    create_user_role("ls-key", "LS Key", "editor", user_id=uid)
    caller = provide_caller(_FakeRequest({"X-API-Key": "ls-key"}))  # type: ignore[arg-type]
    assert caller.role == "editor"
    assert caller.user_id == uid


def test_require_role_passes_authorized(isolated_db):
    caller = Caller(api_key="x", role="admin", user_id=None)
    # require_role returns a Provide(...); unwrap to the underlying check.
    fn = require_role("admin", "editor").dependency
    assert fn(caller) is caller


def test_require_role_rejects_unauthorized(isolated_db):
    caller = Caller(api_key="x", role="viewer", user_id=None)
    fn = require_role("admin", "editor").dependency
    with pytest.raises(PermissionDeniedException):
        fn(caller)
