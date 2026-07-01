"""/admin/policies router tests (23-04, SC4).

Mirrors test_bot_health_routes.py / test_model_cache_routes.py for auth wiring:
spin up a TestClient with policies_router + ApiKeyMiddleware, plant a real admin
user/role in the DB, then drive the CRUD round-trip + /decision route with
X-API-Key.
"""

from __future__ import annotations

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


@pytest.fixture
def client(isolated_db):
    """Test client mounting policies_router with ApiKeyMiddleware."""
    from litestar.testing import create_test_client

    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.policies import policies_router

    with create_test_client(
        route_handlers=[policies_router],
        middleware=[ApiKeyMiddleware()],
    ) as c:
        yield c


def _hdr(key):
    return {"X-API-Key": key}


# ---------------------------------------------------------------------------
# CRUD round-trip
# ---------------------------------------------------------------------------


def test_crud_round_trip(client):
    """PUT creates a session-scope deny row, GET lists it, DELETE removes it."""
    key = _setup_admin_user()

    # PUT — create.
    r = client.put(
        "/admin/policies",
        json={
            "scope": "session",
            "scope_id": "sess-1",
            "kind": "ask_on_os_tools",
            "effect": "deny",
            "priority": 5,
            "params": {"kinds": ["shell"]},
        },
        headers=_hdr(key),
    )
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["scope"] == "session"
    assert created["effect"] == "deny"
    assert created["params"] == {"kinds": ["shell"]}
    pol_id = created["id"]
    assert pol_id.startswith("pol-")

    # GET — list shows it.
    r = client.get("/admin/policies", headers=_hdr(key))
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["policies"]]
    assert pol_id in ids

    # GET — scope filter.
    r = client.get("/admin/policies?scope=session", headers=_hdr(key))
    assert r.status_code == 200
    assert all(p["scope"] == "session" for p in r.json()["policies"])

    # DELETE — removes it.
    r = client.delete(f"/admin/policies/{pol_id}", headers=_hdr(key))
    assert r.status_code in (200, 204)

    r = client.get("/admin/policies", headers=_hdr(key))
    assert pol_id not in [p["id"] for p in r.json()["policies"]]


def test_put_update_existing(client):
    """PUT with an id updates the row rather than creating a new one."""
    key = _setup_admin_user()
    r = client.put(
        "/admin/policies",
        json={"scope": "server", "kind": "cost_budget", "effect": "ask"},
        headers=_hdr(key),
    )
    pol_id = r.json()["id"]

    r = client.put(
        "/admin/policies",
        json={"id": pol_id, "effect": "deny", "priority": 9},
        headers=_hdr(key),
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["id"] == pol_id
    assert updated["effect"] == "deny"
    assert updated["priority"] == 9

    # Only one row total.
    r = client.get("/admin/policies", headers=_hdr(key))
    assert len([p for p in r.json()["policies"] if p["id"] == pol_id]) == 1


def test_put_rejects_bad_input(client):
    key = _setup_admin_user()
    for bad in (
        {"scope": "bogus", "kind": "cost_budget"},
        {"scope": "server", "kind": "not_a_kind"},
        {"scope": "server", "kind": "cost_budget", "effect": "maybe"},
        {"kind": "cost_budget"},  # missing scope
    ):
        r = client.put("/admin/policies", json=bad, headers=_hdr(key))
        assert r.status_code == 400, (bad, r.text)


def test_delete_missing_is_404(client):
    key = _setup_admin_user()
    r = client.delete("/admin/policies/pol-nope", headers=_hdr(key))
    assert r.status_code == 404


def test_update_missing_is_404(client):
    key = _setup_admin_user()
    r = client.put(
        "/admin/policies",
        json={"id": "pol-nope", "effect": "deny"},
        headers=_hdr(key),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /decision route — resolves a pending ASK
# ---------------------------------------------------------------------------


def test_decision_resolves_pending_ask(client):
    """POST /decision forwards to submit_policy_decision and reports ok=True when
    a wait was pending; ok=False otherwise."""
    key = _setup_admin_user()
    from app.services import policy_service as ps_mod

    sid = "sess-decide"
    aid = "ask-decide"  # FIX 2 — decisions are scoped to a unique ask_id.
    # No pending wait yet → ok False (but the decision is still recorded).
    r = client.post(
        "/admin/policies/decision",
        json={"session_id": sid, "ask_id": aid, "decision": "approve"},
        headers=_hdr(key),
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"ok": False}

    # Simulate a pending ASK (await_decision seeds None keyed by ask_id) then
    # resolve it.
    ps_mod._POLICY_DECISIONS[aid] = None
    r = client.post(
        "/admin/policies/decision",
        json={"session_id": sid, "ask_id": aid, "decision": "deny", "message": "no"},
        headers=_hdr(key),
    )
    assert r.status_code == 201
    assert r.json() == {"ok": True}
    # The decision tuple is now recorded (keyed by ask_id) for the poll loop.
    assert ps_mod._POLICY_DECISIONS[aid] == ("deny", "no")
    ps_mod._POLICY_DECISIONS.pop(aid, None)


def test_decision_rejects_bad_input(client):
    key = _setup_admin_user()
    r = client.post(
        "/admin/policies/decision",
        json={"ask_id": "a", "decision": "approve"},  # missing session_id
        headers=_hdr(key),
    )
    assert r.status_code == 400
    r = client.post(
        "/admin/policies/decision",
        json={"session_id": "s", "decision": "approve"},  # missing ask_id (FIX 2)
        headers=_hdr(key),
    )
    assert r.status_code == 400
    r = client.post(
        "/admin/policies/decision",
        json={"session_id": "s", "ask_id": "a", "decision": "maybe"},  # bad decision
        headers=_hdr(key),
    )
    assert r.status_code == 400


def test_requires_auth(client):
    """With keys planted (so not in bootstrap mode), a no-key request is rejected."""
    _setup_admin_user()  # plant a key so has_any_keys() is True
    r = client.get("/admin/policies")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# BLOCKER 2: the /admin/policies router is admin-gated (mutations + /decision).
# ---------------------------------------------------------------------------


def _setup_user(role: str, email: str):
    """Plant a user with an arbitrary role and return its API key."""
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (email, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    assert create_user_role(api_key, label="t", role=role, user_id=email) is not None
    return api_key


def test_non_admin_forbidden_on_mutations_and_decision(client):
    """A non-admin (editor — the coarse /admin/ default that COULD previously
    PUT/POST) is 403'd on PUT, DELETE AND POST /decision. Policies are the
    governance substrate, so they are admin-only."""
    editor_key = _setup_user("editor", "ed@test")

    # PUT (create/update) — was editor-allowed by the coarse default.
    r = client.put(
        "/admin/policies",
        json={"scope": "server", "kind": "cost_budget", "effect": "ask"},
        headers=_hdr(editor_key),
    )
    assert r.status_code == 403, r.text

    # POST /decision — resolving a pending ASK is a governance action.
    r = client.post(
        "/admin/policies/decision",
        json={"session_id": "s", "decision": "approve"},
        headers=_hdr(editor_key),
    )
    assert r.status_code == 403, r.text

    # DELETE.
    r = client.delete("/admin/policies/pol-x", headers=_hdr(editor_key))
    assert r.status_code == 403, r.text


def test_viewer_forbidden_on_list(client):
    """A viewer cannot even list policies — the whole router is admin-gated."""
    viewer_key = _setup_user("viewer", "vw@test")
    r = client.get("/admin/policies", headers=_hdr(viewer_key))
    assert r.status_code == 403, r.text


def test_admin_allowed_on_mutations(client):
    """Regression guard: the same routes succeed for a real admin principal."""
    admin_key = _setup_admin_user("ad2@test")
    r = client.put(
        "/admin/policies",
        json={"scope": "server", "kind": "cost_budget", "effect": "ask"},
        headers=_hdr(admin_key),
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/admin/policies/decision",
        json={"session_id": "s", "ask_id": "a", "decision": "approve"},
        headers=_hdr(admin_key),
    )
    assert r.status_code == 201, r.text
