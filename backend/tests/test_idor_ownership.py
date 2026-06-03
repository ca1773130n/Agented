"""Regression: per-object ownership enforcement on projects/agents (IDOR H1/H2).

Owner and admin can access; a different non-admin user gets 404; legacy/unowned
rows stay shared. Ownership is recorded on create from the authenticated caller.
"""


def _mk_user(user_id: str) -> None:
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, user_id, "x"),
        )
        conn.commit()


def test_get_owner_helper_and_can_access(isolated_db):
    from app.db.owned_entities import can_access, get_owner
    from app.db.projects import create_project

    _mk_user("alice@test")
    pid = create_project(name="owned", user_id="alice@test")
    assert get_owner("projects", pid) == "alice@test"

    # Owner and admin pass; a different non-admin user is denied.
    assert can_access("projects", pid, "alice@test", "editor") is True
    assert can_access("projects", pid, "bob@test", "admin") is True
    assert can_access("projects", pid, "bob@test", "editor") is False

    # Unowned (legacy) and non-existent rows are shared / pass-through.
    _mk_user("legacy@local")
    legacy = create_project(name="legacy", user_id="legacy@local")
    assert can_access("projects", legacy, "bob@test", "viewer") is True
    assert can_access("projects", "proj-nope", "bob@test", "viewer") is True


def test_create_agent_records_owner(isolated_db):
    from app.db.owned_entities import get_owner
    from app.services.agent_service import AgentService

    _mk_user("carol@test")
    body, status = AgentService.create_agent({"name": "mine"}, user_id="carol@test")
    assert status == 201
    assert get_owner("agents", body["agent_id"]) == "carol@test"


def test_create_agent_ignores_body_user_id(isolated_db):
    # Even if a client tries to set user_id in the body, the service param wins.
    from app.db.owned_entities import get_owner
    from app.services.agent_service import AgentService

    _mk_user("dave@test")
    body, status = AgentService.create_agent(
        {"name": "x", "user_id": "attacker@evil"}, user_id="dave@test"
    )
    assert get_owner("agents", body["agent_id"]) == "dave@test"
