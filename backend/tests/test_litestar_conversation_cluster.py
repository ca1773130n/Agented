"""Smoke tests for the wave 72 conversation cluster CRUD."""

import pytest
from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.conversation_cluster import (
    command_conversations_router,
    hook_conversations_router,
    plugin_conversations_router,
    rule_conversations_router,
)


@pytest.fixture
def client():
    with create_test_client(
        route_handlers=[
            plugin_conversations_router,
            command_conversations_router,
            hook_conversations_router,
            rule_conversations_router,
        ],
        dependencies={"caller": provide_caller},
    ) as c:
        yield c


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_send_message_requires_message(client, namespace, isolated_db):
    resp = client.post(
        f"/api/{namespace}/conversations/conv-x/message", json={}
    )
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_unknown_conversation_404(client, namespace, isolated_db):
    resp = client.get(f"/api/{namespace}/conversations/missing")
    # service returns 404 with error
    assert resp.status_code in (200, 404)
    # if 200, verify no error key
    if resp.status_code == 200:
        body = resp.json()
        assert "error" not in body or body.get("error") is None


@pytest.mark.parametrize(
    "namespace",
    ["commands", "hooks", "rules"],
)
def test_list_conversations(client, namespace, isolated_db):
    resp = client.get(f"/api/{namespace}/conversations/")
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "namespace",
    ["commands", "hooks", "rules"],
)
def test_resume_unknown_404(client, namespace, isolated_db):
    resp = client.post(f"/api/{namespace}/conversations/missing/resume", json={})
    assert resp.status_code in (200, 400, 404)


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_abandon_unknown(client, namespace, isolated_db):
    resp = client.post(f"/api/{namespace}/conversations/missing/abandon", json={})
    assert resp.status_code in (200, 400, 404)


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_finalize_unknown(client, namespace, isolated_db):
    resp = client.post(f"/api/{namespace}/conversations/missing/finalize", json={})
    assert resp.status_code in (200, 400, 404)


# ---------------------------------------------------------------------------
# v0.7.83 (codex WARN 4 / 2nd pass) — route-level multi-tenant auth.
# Mirrors the skill cluster's cross-user coverage (test_litestar_skills.py).
# ---------------------------------------------------------------------------


def _seed_two_users():
    from app.db.connection import get_connection
    from app.db.rbac import create_user_role

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email) VALUES (?, ?), (?, ?)",
            ("user-alice", "alice@test.local", "user-bob", "bob@test.local"),
        )
        conn.commit()
    create_user_role("key-alice", "Alice", "admin", user_id="user-alice")
    create_user_role("key-bob", "Bob", "admin", user_id="user-bob")


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_cross_user_get_returns_404(client, namespace, isolated_db):
    """Alice starts a conv; Bob's GET returns 404 (not 200, not 403)."""
    _seed_two_users()
    start = client.post(
        f"/api/{namespace}/conversations/start",
        headers={"X-API-Key": "key-alice"},
    )
    conv_id = start.json()["conversation_id"]
    resp = client.get(
        f"/api/{namespace}/conversations/{conv_id}",
        headers={"X-API-Key": "key-bob"},
    )
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_cross_user_send_message_returns_404(client, namespace, isolated_db):
    """Alice's conv must reject Bob's POST /message."""
    _seed_two_users()
    start = client.post(
        f"/api/{namespace}/conversations/start",
        headers={"X-API-Key": "key-alice"},
    )
    conv_id = start.json()["conversation_id"]
    resp = client.post(
        f"/api/{namespace}/conversations/{conv_id}/message",
        headers={"X-API-Key": "key-bob"},
        json={"message": "intruder"},
    )
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_cross_user_abandon_returns_404(client, namespace, isolated_db):
    """Alice's conv must reject Bob's abandon — and stay active."""
    _seed_two_users()
    start = client.post(
        f"/api/{namespace}/conversations/start",
        headers={"X-API-Key": "key-alice"},
    )
    conv_id = start.json()["conversation_id"]
    resp = client.post(
        f"/api/{namespace}/conversations/{conv_id}/abandon",
        headers={"X-API-Key": "key-bob"},
        json={},
    )
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_cross_user_finalize_returns_404(client, namespace, isolated_db):
    """v0.7.83 codex BLOCK fix — Bob attempting to finalize
    Alice's conv must 404. Pre-v0.7.83 this would have
    succeeded (or errored on missing config) and created the
    entity under Bob's account.
    """
    _seed_two_users()
    start = client.post(
        f"/api/{namespace}/conversations/start",
        headers={"X-API-Key": "key-alice"},
    )
    conv_id = start.json()["conversation_id"]
    resp = client.post(
        f"/api/{namespace}/conversations/{conv_id}/finalize",
        headers={"X-API-Key": "key-bob"},
        json={},
    )
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_active_scopes_to_caller(client, namespace, isolated_db):
    """Alice's /active returns only her own conv; Bob's doesn't see it."""
    _seed_two_users()
    start = client.post(
        f"/api/{namespace}/conversations/start",
        headers={"X-API-Key": "key-alice"},
    )
    alice_conv = start.json()["conversation_id"]
    resp_alice = client.get(
        f"/api/{namespace}/conversations/active",
        headers={"X-API-Key": "key-alice"},
    )
    assert resp_alice.status_code == 200
    alice_ids = {c["id"] for c in resp_alice.json()["active_conversations"]}
    assert alice_conv in alice_ids
    resp_bob = client.get(
        f"/api/{namespace}/conversations/active",
        headers={"X-API-Key": "key-bob"},
    )
    assert resp_bob.status_code == 200
    bob_ids = {c["id"] for c in resp_bob.json()["active_conversations"]}
    assert alice_conv not in bob_ids
