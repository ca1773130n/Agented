"""Redispatch route + startup auto-recovery (Phase 4, Unit A)."""

from unittest.mock import patch

from litestar.testing import create_test_client

from app.db.execution_logs import create_execution_log, update_execution_log
from app.services.execution_service import ExecutionService
from app_litestar.auth import provide_caller
from app_litestar.routes.executions import executions_router


def _client():
    return create_test_client(
        route_handlers=[executions_router],
        dependencies={"caller": provide_caller},
    )


def _make_execution(execution_id="exec-1", trigger_id="bot-pr-review", status="interrupted"):
    create_execution_log(
        execution_id=execution_id,
        trigger_id=trigger_id,
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="stored prompt",
        backend_type="claude",
        command="echo hi",
    )
    update_execution_log(execution_id, status=status, finished_at="2026-06-11T00:01:00")


def test_route_redispatches():
    _make_execution()
    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"execution_id": "exec-new"}
    ) as svc:
        with _client() as client:
            resp = client.post("/admin/executions/exec-1/redispatch")
    assert resp.status_code in (200, 201)
    assert resp.json()["execution_id"] == "exec-new"
    svc.assert_called_once_with("exec-1")


def test_route_maps_errors_to_4xx():
    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"error": "not_found"}
    ):
        with _client() as client:
            assert client.post("/admin/executions/nope/redispatch").status_code == 404
    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"error": "already_redispatched"}
    ):
        with _client() as client:
            assert client.post("/admin/executions/x/redispatch").status_code == 409
    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"error": "not_eligible"}
    ):
        with _client() as client:
            assert client.post("/admin/executions/x/redispatch").status_code == 409


def test_auto_redispatch_only_opted_in_triggers():
    """Startup recovery touches only interrupted executions whose trigger has
    auto_redispatch=1, and skips rows that already have a redispatch child."""
    from app.db.connection import get_connection

    _make_execution("exec-a", status="interrupted")  # trigger NOT opted in
    _make_execution("exec-b", status="interrupted")
    with get_connection() as conn:  # opt the trigger in for exec-b only via a 2nd trigger
        conn.execute(
            "INSERT INTO triggers (id, name, prompt_template, auto_redispatch) "
            "VALUES ('trig-auto', 'T', 'tpl', 1)"
        )
        conn.execute(
            "UPDATE execution_logs SET trigger_id = 'trig-auto' WHERE execution_id = 'exec-b'"
        )
        conn.commit()

    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"execution_id": "exec-new"}
    ) as svc:
        count = ExecutionService.auto_redispatch_interrupted()
    assert count == 1
    svc.assert_called_once_with("exec-b")


def test_trigger_update_accepts_auto_redispatch():
    from app.db.connection import get_connection
    from app.db.triggers import get_trigger, update_trigger

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO triggers (id, name, prompt_template) VALUES ('trig-u', 'T', 'tpl')"
        )
        conn.commit()
    assert update_trigger("trig-u", auto_redispatch=1) is not False
    assert get_trigger("trig-u")["auto_redispatch"] == 1
