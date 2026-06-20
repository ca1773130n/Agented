"""Smoke tests for the Litestar skills cluster (wave 57)."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.skills import (
    skill_conversations_router,
    skill_sets_router,
    skills_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            health_router,
            # /api/skills/conversations registered first so its prefix takes
            # precedence over /api/skills/{skill_name} catches.
            skill_conversations_router,
            skills_router,
            skill_sets_router,
        ],
        dependencies={"caller": provide_caller},
    )


def test_list_skills_bootstrap(isolated_db):
    with _client() as c:
        resp = c.get("/api/skills/")
    assert resp.status_code == 200


def test_unknown_skill_404(isolated_db):
    create_user_role("admin-key-skill", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/api/skills/discover/missing-skill",
            headers={"X-API-Key": "admin-key-skill"},
        )
    # SkillsService returns NOT_FOUND tuple → 404
    assert resp.status_code == 404


def test_user_skills_list(isolated_db):
    create_user_role("admin-key-us", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/api/skills/user",
            headers={"X-API-Key": "admin-key-us"},
        )
    assert resp.status_code == 200


def test_harness_config(isolated_db):
    create_user_role("admin-key-hc", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/api/skills/harness/config",
            headers={"X-API-Key": "admin-key-hc"},
        )
    assert resp.status_code in (200, 404, 500)  # depends on harness state


def test_skill_sets_list(isolated_db):
    with _client() as c:
        resp = c.get("/api/skill-sets/")
    assert resp.status_code == 200
    assert "skill_sets" in resp.json()


def test_skill_set_create_rejects_empty_name(isolated_db):
    create_user_role("admin-key-ss", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/api/skill-sets/",
            headers={"X-API-Key": "admin-key-ss"},
            json={"name": ""},
        )
    assert resp.status_code == 400


def test_skill_set_update_unknown_404(isolated_db):
    create_user_role("admin-key-ss2", "Admin", "admin")
    with _client() as c:
        resp = c.put(
            "/api/skill-sets/missing-id",
            headers={"X-API-Key": "admin-key-ss2"},
            json={"name": "x"},
        )
    assert resp.status_code == 404


def test_conversation_unknown_404(isolated_db):
    create_user_role("admin-key-conv", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/api/skills/conversations/missing-id",
            headers={"X-API-Key": "admin-key-conv"},
        )
    # Service returns NOT_FOUND tuple → 404
    assert resp.status_code == 404


def test_send_message_requires_message(isolated_db):
    create_user_role("admin-key-conv2", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/api/skills/conversations/foo/message",
            headers={"X-API-Key": "admin-key-conv2"},
            json={},
        )
    assert resp.status_code == 400


# v0.7.78 (codex BLOCK 1+2 / WARN 3) — route-level auth tests.
# These cover ownership enforcement on conv-id endpoints and the
# /active list scoping so a regression that re-exposes another
# user's conv (or every active conv to a bootstrap caller) gets
# caught here, not in production.


def _seed_two_users():
    """Create two users + an API key for each. The second user
    gets an explicit user_id so the two keys map to distinct
    operators."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email) VALUES (?, ?), (?, ?)",
            ("user-alice", "alice@test.local", "user-bob", "bob@test.local"),
        )
        conn.commit()
    create_user_role("key-alice", "Alice", "admin", user_id="user-alice")
    create_user_role("key-bob", "Bob", "admin", user_id="user-bob")


def test_active_list_scopes_to_caller_user(isolated_db):
    """Alice's /active must show only Alice's active convs."""
    _seed_two_users()
    from app.db import create_skill_conversation

    create_skill_conversation(
        "skill_aliceconv1aaaa",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-alice",
    )
    create_skill_conversation(
        "skill_bobconvxxxbbbb",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-bob",
    )
    with _client() as c:
        resp = c.get(
            "/api/skills/conversations/active",
            headers={"X-API-Key": "key-alice"},
        )
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()["active_conversations"]}
    assert "skill_aliceconv1aaaa" in ids
    assert "skill_bobconvxxxbbbb" not in ids


def test_get_conversation_rejects_cross_user(isolated_db):
    """Bob asking for Alice's conv must 404 (not 200, not 403)."""
    _seed_two_users()
    from app.db import create_skill_conversation

    create_skill_conversation(
        "skill_aliceownedaaa1",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-alice",
    )
    with _client() as c:
        resp = c.get(
            "/api/skills/conversations/skill_aliceownedaaa1",
            headers={"X-API-Key": "key-bob"},
        )
    assert resp.status_code == 404


def test_send_message_rejects_cross_user(isolated_db):
    """Bob posting to Alice's conv must 404."""
    _seed_two_users()
    from app.db import create_skill_conversation

    create_skill_conversation(
        "skill_alicesendsaaa1",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-alice",
    )
    with _client() as c:
        resp = c.post(
            "/api/skills/conversations/skill_alicesendsaaa1/message",
            headers={"X-API-Key": "key-bob"},
            json={"message": "hello"},
        )
    assert resp.status_code == 404


def test_abandon_rejects_cross_user(isolated_db):
    """Bob abandoning Alice's conv must 404 — and the row stays active."""
    _seed_two_users()
    from app.db import create_skill_conversation, get_skill_conversation

    create_skill_conversation(
        "skill_alicedontkillaa",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-alice",
    )
    with _client() as c:
        resp = c.post(
            "/api/skills/conversations/skill_alicedontkillaa/abandon",
            headers={"X-API-Key": "key-bob"},
        )
    assert resp.status_code == 404
    # Alice's conv is still active — bob couldn't tear it down.
    row = get_skill_conversation("skill_alicedontkillaa")
    assert row["status"] == "active"


def test_stream_rejects_cross_user_with_404(isolated_db):
    """v0.7.78 (codex WARN B / 2nd pass) — the SSE stream route
    must return a real 404 for a cross-user probe, not a 200 with
    an in-band ``event: error`` body. Without the precheck the
    error rule was inconsistent with the other conv-id endpoints.
    """
    _seed_two_users()
    from app.db import create_skill_conversation

    create_skill_conversation(
        "skill_alicestreamssss",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-alice",
    )
    with _client() as c:
        resp = c.get(
            "/api/skills/conversations/skill_alicestreamssss/stream",
            headers={"X-API-Key": "key-bob"},
        )
    assert resp.status_code == 404


def test_active_userless_caller_only_sees_null_owned(isolated_db):
    """No-auth (bootstrap) caller must NOT see user-owned convs.

    Previously list_active(user_id=None) returned every row;
    after BLOCK 1 the helper scopes to ``user_id IS NULL`` so a
    bootstrap caller sees only legacy unowned rows.
    """
    _seed_two_users()
    from app.db import create_skill_conversation

    create_skill_conversation(
        "skill_userownedxxxxx",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-alice",
    )
    create_skill_conversation(
        "skill_unownedlegacyyy",
        [{"role": "system", "content": "s", "timestamp": "t"}],
    )
    # Use a fresh isolated_db with NO user_roles → bootstrap path.
    # Re-running create_user_role would lock us out of bootstrap;
    # for this test we drop the role rows so the dependency
    # resolves a bootstrap Caller (admin role, user_id=None).
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("DELETE FROM user_roles")
        conn.commit()
    with _client() as c:
        resp = c.get("/api/skills/conversations/active")
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()["active_conversations"]}
    assert "skill_unownedlegacyyy" in ids
    assert "skill_userownedxxxxx" not in ids
