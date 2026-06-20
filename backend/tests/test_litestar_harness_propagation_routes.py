"""Route smoke tests for forge propagation endpoints.

Exercises:
- ``GET /admin/shared-forge`` → returns shared list (empty when no promoted bindings)
- ``POST /admin/projects/{project_id}/adopt-shared/{shared_binding_id}`` →
  not_found when shared binding missing; adopts a created shared binding
"""

from __future__ import annotations

from litestar.testing import create_test_client

from app.database import get_connection
from app_litestar.auth import provide_caller
from app_litestar.routes.harness_evolution import harness_evolution_router


def _client():
    return create_test_client(
        route_handlers=[harness_evolution_router],
        dependencies={"caller": provide_caller},
    )


def test_list_shared_forge_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/shared-forge")
    assert resp.status_code == 200
    body = resp.json()
    assert "shared" in body
    assert isinstance(body["shared"], list)


def test_adopt_shared_not_found(isolated_db):
    with _client() as c:
        resp = c.post("/admin/projects/proj-test/adopt-shared/9999")
    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == "proj-test"
    assert body["adopted"] is False
    assert body["reason"] == "not_found"


def test_adopt_shared_adopts_existing(isolated_db):
    from app.db.forge_promotion import create_shared_binding

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-adopt', 'P', 'active')")
        conn.commit()

    sb_id = create_shared_binding(scope="global", kind="rule", asset_id="1", fingerprint="abc123")
    assert sb_id is not None

    with _client() as c:
        resp = c.post(f"/admin/projects/proj-adopt/adopt-shared/{sb_id}")
    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == "proj-adopt"
    assert body["adopted"] is True
