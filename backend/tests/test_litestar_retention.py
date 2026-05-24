"""PR-R (wave 83): end-to-end tests for /admin/retention-policies/* via Litestar."""

from __future__ import annotations

from litestar.testing import create_test_client

from app_litestar.routes.retention import retention_router


def _client():
    return create_test_client(route_handlers=[retention_router])


def test_list_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/retention-policies/")
    assert resp.status_code == 200
    assert resp.json() == {"policies": []}


def test_create_then_list_roundtrip(isolated_db):
    payload = {
        "category": "execution_logs",
        "scope": "team",
        "scope_name": "Platform Team",
        "retention_days": 14,
        "delete_on_expiry": True,
        "archive_on_expiry": False,
        "estimated_size_gb": 0.5,
    }
    with _client() as c:
        created = c.post("/admin/retention-policies/", json=payload)
        assert created.status_code == 201
        body = created.json()
        assert body["id"].startswith("ret-")
        assert body["category"] == "execution_logs"
        assert body["retention_days"] == 14
        assert body["enabled"] == 1

        listed = c.get("/admin/retention-policies/")
    assert listed.status_code == 200
    policies = listed.json()["policies"]
    assert len(policies) == 1
    assert policies[0]["id"] == body["id"]


def test_create_unknown_category_400(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/retention-policies/",
            json={"category": "totally_bogus", "retention_days": 30},
        )
    assert resp.status_code == 400


def test_create_retention_days_zero_400(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/retention-policies/",
            json={"category": "audit_logs", "retention_days": 0},
        )
    assert resp.status_code == 400


def test_toggle_flips_enabled(isolated_db):
    with _client() as c:
        created = c.post(
            "/admin/retention-policies/",
            json={"category": "bot_memory", "retention_days": 30},
        ).json()
        policy_id = created["id"]

        toggle_off = c.patch(
            f"/admin/retention-policies/{policy_id}/toggle",
            json={"enabled": False},
        )
        assert toggle_off.status_code == 200
        assert toggle_off.json() == {"id": policy_id, "enabled": False}

        listed = c.get("/admin/retention-policies/").json()["policies"]
    assert listed[0]["enabled"] == 0


def test_toggle_unknown_id_404(isolated_db):
    with _client() as c:
        resp = c.patch(
            "/admin/retention-policies/ret-bogus/toggle",
            json={"enabled": True},
        )
    assert resp.status_code == 404


def test_toggle_missing_enabled_400(isolated_db):
    with _client() as c:
        created = c.post(
            "/admin/retention-policies/",
            json={"category": "token_metrics", "retention_days": 60},
        ).json()
        resp = c.patch(
            f"/admin/retention-policies/{created['id']}/toggle",
            json={},
        )
    assert resp.status_code == 400


def test_delete_removes(isolated_db):
    with _client() as c:
        created = c.post(
            "/admin/retention-policies/",
            json={"category": "execution_outputs", "retention_days": 7},
        ).json()
        policy_id = created["id"]

        resp = c.delete(f"/admin/retention-policies/{policy_id}")
        assert resp.status_code == 204

        listed = c.get("/admin/retention-policies/").json()["policies"]
    assert listed == []


def test_delete_unknown_id_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/retention-policies/ret-bogus")
    assert resp.status_code == 404


def test_cleanup_returns_message(isolated_db):
    with _client() as c:
        c.post(
            "/admin/retention-policies/",
            json={"category": "execution_logs", "retention_days": 30},
        )
        resp = c.post("/admin/retention-policies/cleanup")
    assert resp.status_code == 201
    body = resp.json()
    assert "message" in body
    assert "queued" in body["message"].lower()
