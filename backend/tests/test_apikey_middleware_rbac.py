"""v0.5.12: ApiKeyMiddleware enforces role + rotates session token."""

from litestar import delete, get, post
from litestar.testing import create_test_client


def _setup_user_with_role(role: str, email: str = "u@test") -> tuple[str, str]:
    """Create user + role + session. Returns (api_key, session_token)."""
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key
    from app.db.sessions import create_session

    user_id = email
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    role_id = create_user_role(api_key, label="t", role=role, user_id=user_id)
    assert role_id is not None
    sess = create_session(user_id)
    return api_key, sess["token"]


@get("/admin/agents", sync_to_thread=False)
def list_agents() -> dict:
    return {"agents": []}


@post("/admin/agents", sync_to_thread=False)
def create_agent() -> dict:
    return {"created": True}


@delete("/admin/agents/{agent_id:str}", status_code=200, sync_to_thread=False)
def delete_agent(agent_id: str) -> dict:
    return {"deleted": agent_id}


def _client():
    from app_litestar.middleware import ApiKeyMiddleware

    return create_test_client(
        route_handlers=[list_agents, create_agent, delete_agent],
        middleware=[ApiKeyMiddleware()],
    )


class TestRbacEnforcement:
    def test_viewer_can_get_admin(self, isolated_db):
        api_key, _ = _setup_user_with_role("viewer")
        with _client() as c:
            resp = c.get("/admin/agents", headers={"X-API-Key": api_key})
        assert resp.status_code == 200

    def test_viewer_cannot_post_admin(self, isolated_db):
        api_key, _ = _setup_user_with_role("viewer")
        with _client() as c:
            resp = c.post("/admin/agents", headers={"X-API-Key": api_key})
        assert resp.status_code == 403

    def test_editor_can_post_admin(self, isolated_db):
        api_key, _ = _setup_user_with_role("editor")
        with _client() as c:
            resp = c.post("/admin/agents", headers={"X-API-Key": api_key})
        assert resp.status_code in (200, 201)

    def test_editor_cannot_delete_admin(self, isolated_db):
        api_key, _ = _setup_user_with_role("editor")
        with _client() as c:
            resp = c.delete("/admin/agents/foo", headers={"X-API-Key": api_key})
        assert resp.status_code == 403

    def test_admin_can_delete_admin(self, isolated_db):
        api_key, _ = _setup_user_with_role("admin")
        with _client() as c:
            resp = c.delete("/admin/agents/foo", headers={"X-API-Key": api_key})
        assert resp.status_code == 200

    def test_unauthenticated_returns_401(self, isolated_db):
        # Provision at least one role so bootstrap mode doesn't bypass.
        _setup_user_with_role("admin")
        with _client() as c:
            resp = c.get("/admin/agents")
        assert resp.status_code == 401


class TestSessionRotation:
    def test_session_response_includes_x_new_session_token(self, isolated_db):
        api_key, token = _setup_user_with_role("viewer")
        with _client() as c:
            resp = c.get(
                "/admin/agents",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.headers.get("x-new-session-token") is not None
        assert resp.headers.get("x-new-session-token") != token
