"""GET /executions/{id}/state — composed Phase 1-3 snapshot (Phase 3 P7)."""

from litestar.testing import create_test_client

from app.db import harness_state
from app.db import verification_records as vr
from app.db.budgets import set_budget_limit
from app_litestar.auth import provide_caller
from app_litestar.routes.executions import executions_router


def _client():
    return create_test_client(
        route_handlers=[executions_router],
        dependencies={"caller": provide_caller},
    )


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="codex",
        command="echo hi",
    )


def test_state_full_snapshot(isolated_db):
    _make_execution()
    harness_state.record_checkpoint("exec-1", ledger={"lines": []})
    harness_state.update_budget_used("exec-1", 0.42)
    vr.record_verification("exec-1", "no secrets", status="passed")
    set_budget_limit("trigger", "bot-pr-review", per_run_limit_usd=2.0)

    with _client() as client:
        # executions_router mounts at path="/admin" (executions.py ~:562)
        resp = client.get("/admin/executions/exec-1/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution"]["status"] == "running"
    assert body["execution"]["backend_type"] == "codex"
    assert body["run"]["budget_used"] == 0.42
    assert body["run"]["step_cursor"] == 1
    assert body["latest_checkpoint"]["step"] == 1
    assert body["checkpoint_count"] == 1
    assert body["verifications"][0]["claim"] == "no secrets"
    assert body["per_run_limit_usd"] == 2.0


def test_state_nulls_for_bare_execution(isolated_db):
    """Pre-Phase-1 rows (no run/checkpoints/verifications) must not 500."""
    _make_execution("exec-bare")
    with _client() as client:
        resp = client.get("/admin/executions/exec-bare/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"] is None
    assert body["latest_checkpoint"] is None
    assert body["checkpoint_count"] == 0
    assert body["verifications"] == []
    assert body["per_run_limit_usd"] is None


def test_state_404_for_unknown_execution(isolated_db):
    with _client() as client:
        resp = client.get("/admin/executions/nope/state")
    assert resp.status_code == 404
