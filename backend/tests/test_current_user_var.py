"""Tests for current_user_var ContextVar plumbing (track B, wave 21)."""

import pytest

from app import create_app
from app.db.rbac import create_user_role
from app.db.users import create_user
from app.logging_config import current_user_var


@pytest.fixture()
def probed_app(isolated_db):
    """Fresh app with a probe route that records current_user_var per request."""
    app = create_app({"TESTING": True})
    captures: list[str | None] = []

    @app.route("/_test/user-probe")
    def _probe():
        captures.append(current_user_var.get())
        return {"ok": True}

    return app, captures


class TestCurrentUserVar:
    def test_var_default_is_none(self):
        assert current_user_var.get() is None

    def test_unauthenticated_request_leaves_user_none(self, probed_app):
        app, captures = probed_app
        with app.test_client() as c:
            c.get("/_test/user-probe")
        assert captures == [None]

    def test_authenticated_request_sets_user(self, probed_app):
        app, captures = probed_app
        uid = create_user("ctx@example.com", "Ctx")
        create_user_role("ctx-key", "Ctx Key", "admin", user_id=uid)
        with app.test_client() as c:
            c.get("/_test/user-probe", headers={"X-API-Key": "ctx-key"})
        assert captures == [uid]

    def test_unknown_api_key_leaves_user_none(self, probed_app):
        app, captures = probed_app
        with app.test_client() as c:
            c.get("/_test/user-probe", headers={"X-API-Key": "not-a-real-key"})
        assert captures == [None]

    def test_var_cleared_on_teardown(self, probed_app):
        app, _ = probed_app
        uid = create_user("teardown@example.com", "Teardown")
        create_user_role("td-key", "Td Key", "admin", user_id=uid)
        with app.test_client() as c:
            c.get("/admin/triggers/", headers={"X-API-Key": "td-key"})
        # Outside the request lifecycle, the var must reset to None.
        assert current_user_var.get() is None
