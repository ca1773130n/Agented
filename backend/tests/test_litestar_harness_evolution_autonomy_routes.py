"""Route smoke tests for autonomy config endpoints.

Exercises:
- ``GET /admin/projects/{project_id}/autonomy`` → returns default policy when unconfigured
- ``PUT /admin/projects/{project_id}/autonomy`` → stores + echoes the policy back
- ``GET`` after ``PUT`` → configured flag flips to True
"""

from __future__ import annotations

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.harness_evolution import harness_evolution_router


def _client():
    return create_test_client(
        route_handlers=[harness_evolution_router],
        dependencies={"caller": provide_caller},
    )


def test_get_autonomy_config_unconfigured(isolated_db):
    with _client() as c:
        resp = c.get("/admin/projects/proj-test/autonomy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "proj-test"
    assert body["configured"] is False
    assert "policy" in body
    assert "enabled" in body["policy"]


def test_put_autonomy_config_stores_and_returns(isolated_db):
    payload = {"policy": {"enabled": True, "confidence_threshold": 0.9, "max_ops_per_round": 3}}
    with _client() as c:
        resp = c.put("/admin/projects/proj-test/autonomy", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "proj-test"
    assert body["policy"]["enabled"] is True
    assert body["policy"]["confidence_threshold"] == 0.9


def test_get_autonomy_config_after_put_shows_configured(isolated_db):
    payload = {"policy": {"enabled": True}}
    with _client() as c:
        c.put("/admin/projects/proj-test/autonomy", json=payload)
        resp = c.get("/admin/projects/proj-test/autonomy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["policy"]["enabled"] is True
