"""Smoke tests for the wave 75 execution routes."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.executions import executions_router


def _client():
    return create_test_client(
        route_handlers=[executions_router],
        dependencies={"caller": provide_caller},
    )


def test_unknown_trigger_executions_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/missing/executions")
    assert resp.status_code == 404


def test_list_all_executions(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions")
    assert resp.status_code == 200


def test_unknown_execution_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/missing")
    assert resp.status_code == 404


def test_unknown_execution_diff_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/missing/diff")
    assert resp.status_code == 404


def test_cancel_unknown_execution_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/executions/missing")
    assert resp.status_code == 404


def test_cancel_post_unknown_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/missing/cancel", json={})
    assert resp.status_code == 404


def test_running_for_unknown_trigger_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/missing/executions/running")
    assert resp.status_code == 404


def test_pause_unknown_execution_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/missing/pause", json={})
    assert resp.status_code == 404


def test_resume_unknown_execution_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/missing/resume", json={})
    assert resp.status_code == 404


def test_bulk_cancel_with_explicit_ids(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/executions/bulk-cancel",
            json={"execution_ids": ["missing-1", "missing-2"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["failed"] == 2


def test_queue_status(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/queue")
    assert resp.status_code == 200


def test_queue_for_trigger(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/queue/missing")
    assert resp.status_code == 200


def test_cancel_queue_for_trigger(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/executions/queue/missing")
    assert resp.status_code == 200


def test_pending_retries(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/retries")
    assert resp.status_code == 200


# PR-G: silent-success stubs flipped to 501. The mutating quota handlers and
# both anomaly endpoints now return 501 ("Feature not yet enabled") so the UI
# can render a banner instead of a fake green state. The GET /quotas read
# stays as an honest empty 200 — the UI renders an empty state for it.


def test_anomalies_returns_501(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/anomalies")
    assert resp.status_code == 501


def test_acknowledge_anomaly_returns_501(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/anomalies/x/acknowledge", json={})
    assert resp.status_code == 501


def test_quotas_get_returns_empty_200(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/quotas")
    assert resp.status_code == 200
    assert resp.json() == {"rules": []}


def test_create_quota_returns_501(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/quotas", json={})
    assert resp.status_code == 501


def test_update_quota_returns_501(isolated_db):
    with _client() as c:
        resp = c.put("/admin/executions/quotas/q-x", json={})
    assert resp.status_code == 501


def test_delete_quota_returns_501(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/executions/quotas/q-x")
    assert resp.status_code == 501
