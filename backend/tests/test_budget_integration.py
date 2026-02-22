"""Integration tests for BudgetService wiring into execution flow (trigger entity)."""

import io
import json
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CLAUDE_JSON_OUTPUT = json.dumps(
    {
        "usage": {
            "input_tokens": 100,
            "output_tokens": 200,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 5,
        },
        "total_cost_usd": 0.005,
        "num_turns": 1,
        "duration_api_ms": 1234,
        "session_id": "sess-test-001",
    }
)


def _make_mock_process(stdout_lines, exit_code=0):
    """Create a mock subprocess.Popen return value with piped stdout/stderr.

    stdout_lines: list of strings (each line, will be newline-terminated).
    """
    proc = MagicMock()
    proc.pid = 12345

    # Build readable pipes using io.StringIO
    stdout_text = "".join(line + "\n" for line in stdout_lines)
    stderr_text = ""

    # Use a real file-like object so readline iteration works
    stdout_pipe = io.StringIO(stdout_text)
    stderr_pipe = io.StringIO(stderr_text)

    proc.stdout = stdout_pipe
    proc.stderr = stderr_pipe
    proc.wait.return_value = exit_code
    proc.returncode = exit_code

    return proc


def _get_test_trigger():
    """Return a minimal trigger dict suitable for run_trigger."""
    return {
        "id": "bot-security",
        "name": "Test Trigger",
        "backend_type": "claude",
        "prompt_template": "Analyze {paths}: {message}",
        "trigger_source": "webhook",
        "skill_command": "",
        "model": None,
        "auto_resolve": False,
    }


# ---------------------------------------------------------------------------
# Test 1: Token usage is extracted and recorded after successful execution
# ---------------------------------------------------------------------------


def test_run_trigger_extracts_and_records_token_usage(isolated_db, monkeypatch):
    """After a successful claude execution, token_usage table should have a record."""
    from app.database import get_connection
    from app.services.execution_service import ExecutionService

    trigger = _get_test_trigger()

    # Mock subprocess.Popen to return a process with exit_code=0 and JSON stdout
    mock_proc = _make_mock_process([_CLAUDE_JSON_OUTPUT])
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *args, **kwargs: mock_proc,
    )

    # Mock ProcessManager to avoid tracking issues
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.register",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.is_cancelled",
        lambda *a, **kw: False,
    )
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.cleanup",
        lambda *a, **kw: None,
    )

    # Mock get_paths_for_trigger_detailed to return empty paths
    monkeypatch.setattr(
        "app.services.execution_service.get_paths_for_trigger_detailed",
        lambda trigger_id: [],
    )

    execution_id = ExecutionService.run_trigger(
        trigger, "test message", trigger_type="manual", account_id=None
    )
    assert execution_id is not None

    # Query token_usage table directly
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM token_usage WHERE execution_id = ?", (execution_id,))
        row = cursor.fetchone()

    assert row is not None, "token_usage record should have been created"
    record = dict(row)
    assert record["input_tokens"] == 100
    assert record["output_tokens"] == 200
    assert record["cache_read_tokens"] == 10
    assert record["total_cost_usd"] == pytest.approx(0.005)
    assert record["entity_type"] == "trigger"
    assert record["entity_id"] == "bot-security"
    assert record["backend_type"] == "claude"


# ---------------------------------------------------------------------------
# Test 2: No crash when stdout has no JSON (opencode-style plain text)
# ---------------------------------------------------------------------------


def test_run_trigger_no_usage_data_no_crash(isolated_db, monkeypatch):
    """run_trigger should complete without error even when stdout has no JSON usage data."""
    from app.database import get_connection
    from app.services.execution_service import ExecutionService

    trigger = _get_test_trigger()
    trigger["backend_type"] = "opencode"

    mock_proc = _make_mock_process(["Running analysis...", "Done."])
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *args, **kwargs: mock_proc,
    )
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.register",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.is_cancelled",
        lambda *a, **kw: False,
    )
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.cleanup",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "app.services.execution_service.get_paths_for_trigger_detailed",
        lambda trigger_id: [],
    )

    execution_id = ExecutionService.run_trigger(
        trigger, "test message", trigger_type="manual", account_id=None
    )
    assert execution_id is not None

    # Token usage table should be empty
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM token_usage WHERE execution_id = ?",
            (execution_id,),
        )
        row = cursor.fetchone()

    assert row["cnt"] == 0, "No token_usage record should exist for opencode backend"


# ---------------------------------------------------------------------------
# Test 3: Hard budget limit blocks execution via fallback chain path
# ---------------------------------------------------------------------------


def test_budget_precheck_blocks_hard_limit(isolated_db, monkeypatch):
    """When hard budget limit is reached, execute_with_fallback returns None
    without calling run_trigger."""
    from app.database import create_token_usage_record, set_budget_limit, set_fallback_chain
    from app.services.execution_service import ExecutionService
    from app.services.orchestration_service import OrchestrationService

    trigger = _get_test_trigger()

    # Set up a fallback chain so the budget pre-check path is exercised
    set_fallback_chain("trigger", trigger["id"], [{"backend_type": "claude"}])

    # Set a hard limit of $0.01
    set_budget_limit("trigger", trigger["id"], period="monthly", hard_limit_usd=0.01)

    # Create execution_logs entry FIRST (FK constraint requires it before token_usage)
    import datetime

    from app.database import create_execution_log

    create_execution_log(
        execution_id="exec-prev-001",
        trigger_id=trigger["id"],
        trigger_type="manual",
        started_at=datetime.datetime.now().isoformat(),
        prompt="test",
        backend_type="claude",
        command="test",
    )

    # Record existing usage that exceeds the hard limit
    create_token_usage_record(
        execution_id="exec-prev-001",
        entity_type="trigger",
        entity_id=trigger["id"],
        backend_type="claude",
        account_id=None,
        input_tokens=500,
        output_tokens=1000,
        total_cost_usd=0.05,  # exceeds $0.01 hard limit
    )

    # Mock run_trigger to track if it gets called
    run_trigger_called = []
    monkeypatch.setattr(
        ExecutionService,
        "run_trigger",
        classmethod(lambda cls, *a, **kw: run_trigger_called.append(True) or "exec-mock"),
    )

    result = OrchestrationService.execute_with_fallback(
        trigger, "test message", trigger_type="manual"
    )

    assert result is None, "execute_with_fallback should return None when hard limit reached"
    assert len(run_trigger_called) == 0, "run_trigger should not have been called"


# ---------------------------------------------------------------------------
# Test 4: Soft budget limit allows execution to proceed
# ---------------------------------------------------------------------------


def test_budget_precheck_allows_soft_limit(isolated_db, monkeypatch):
    """When soft limit is exceeded but hard limit is not, execution should proceed."""
    import datetime

    from app.database import (
        create_execution_log,
        create_token_usage_record,
        set_budget_limit,
        set_fallback_chain,
    )
    from app.services.execution_service import ExecutionService
    from app.services.orchestration_service import OrchestrationService
    from app.services.rate_limit_service import RateLimitService

    trigger = _get_test_trigger()

    # Set up fallback chain
    set_fallback_chain("trigger", trigger["id"], [{"backend_type": "claude"}])

    # Set soft=$0.01, hard=$100 -- spend will exceed soft but not hard
    set_budget_limit(
        "trigger", trigger["id"], period="monthly", soft_limit_usd=0.01, hard_limit_usd=100.0
    )

    # Create execution_logs entry FIRST (FK constraint requires it before token_usage)
    create_execution_log(
        execution_id="exec-prev-002",
        trigger_id=trigger["id"],
        trigger_type="manual",
        started_at=datetime.datetime.now().isoformat(),
        prompt="test",
        backend_type="claude",
        command="test",
    )

    # Record existing usage that exceeds soft limit
    create_token_usage_record(
        execution_id="exec-prev-002",
        entity_type="trigger",
        entity_id=trigger["id"],
        backend_type="claude",
        account_id=None,
        input_tokens=500,
        output_tokens=1000,
        total_cost_usd=0.05,  # exceeds $0.01 soft limit, under $100 hard
    )

    # Mock run_trigger to track that it IS called
    run_trigger_called = []

    @classmethod
    def mock_run_trigger(cls, *args, **kwargs):
        run_trigger_called.append(True)
        return "exec-mock-002"

    monkeypatch.setattr(ExecutionService, "run_trigger", mock_run_trigger)

    # Mock was_rate_limited (execution wasn't rate limited)
    monkeypatch.setattr(
        ExecutionService,
        "was_rate_limited",
        classmethod(lambda cls, eid: None),
    )

    # Mock RateLimitService.pick_best_account to return a valid account
    monkeypatch.setattr(
        RateLimitService,
        "pick_best_account",
        classmethod(
            lambda cls, backend_type: {
                "id": 1,
                "account_name": "test-account",
                "api_key_env": None,
            }
        ),
    )

    # Mock increment_account_executions where it was imported in orchestration_service
    import app.services.orchestration_service as orch_module

    monkeypatch.setattr(orch_module, "increment_account_executions", lambda aid: None)

    result = OrchestrationService.execute_with_fallback(
        trigger, "test message", trigger_type="manual"
    )

    assert result is not None, "execute_with_fallback should proceed when only soft limit exceeded"
    assert len(run_trigger_called) == 1, "run_trigger should have been called exactly once"


# ---------------------------------------------------------------------------
# Test 5: Budget limit creation accepts "trigger" entity_type
# ---------------------------------------------------------------------------


def test_budget_limit_trigger_entity_type(isolated_db):
    """Budget limits can be created and retrieved with entity_type='trigger'."""
    from app.database import get_budget_limit, set_budget_limit
    from app.services.budget_service import BudgetService

    trigger_id = "bot-security"

    # Create a budget limit with entity_type="trigger"
    success = set_budget_limit(
        entity_type="trigger",
        entity_id=trigger_id,
        period="monthly",
        soft_limit_usd=10.0,
        hard_limit_usd=50.0,
    )
    assert success, "set_budget_limit should succeed for trigger entity_type"

    # Retrieve the budget limit
    limit = get_budget_limit("trigger", trigger_id)
    assert limit is not None, "Budget limit should be retrievable for trigger entity_type"
    limit_dict = dict(limit)
    assert limit_dict["entity_type"] == "trigger"
    assert limit_dict["entity_id"] == trigger_id
    assert limit_dict["soft_limit_usd"] == 10.0
    assert limit_dict["hard_limit_usd"] == 50.0

    # check_budget should work for trigger entity_type (no spend yet)
    result = BudgetService.check_budget("trigger", trigger_id)
    assert result["allowed"] is True
    assert result["reason"] == "within_budget"
    assert result["current_spend"] == 0.0


# ---------------------------------------------------------------------------
# Test 6: Budget route accepts "trigger" via API endpoint
# ---------------------------------------------------------------------------


def test_budget_route_accepts_trigger_entity_type(isolated_db):
    """PUT /admin/budgets/limits should accept entity_type='trigger' without 400 error."""
    from app import create_app

    app = create_app()
    with app.test_client() as client:
        # Create a budget limit with entity_type="trigger" via API
        response = client.put(
            "/admin/budgets/limits",
            json={
                "entity_type": "trigger",
                "entity_id": "bot-security",
                "period": "monthly",
                "soft_limit_usd": 5.0,
                "hard_limit_usd": 25.0,
            },
        )
        assert response.status_code == 200, (
            f"Budget limit creation should succeed for trigger, got {response.status_code}: "
            f"{response.get_json()}"
        )
        data = response.get_json()
        assert data["entity_type"] == "trigger"
        assert data["entity_id"] == "bot-security"

        # Verify invalid entity_type still returns 400
        response = client.put(
            "/admin/budgets/limits",
            json={
                "entity_type": "invalid",
                "entity_id": "test-id",
                "soft_limit_usd": 1.0,
            },
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Test 7: Direct run_trigger blocks execution when hard budget limit exceeded
# ---------------------------------------------------------------------------


def test_direct_run_trigger_budget_precheck(isolated_db, monkeypatch):
    """run_trigger should block execution when hard budget limit is exceeded for the trigger,
    without spawning a subprocess."""
    import datetime

    from app.database import (
        create_execution_log,
        create_token_usage_record,
        get_connection,
        set_budget_limit,
    )
    from app.services.execution_service import ExecutionService

    trigger = _get_test_trigger()

    # Set a hard limit of $0.01
    set_budget_limit("trigger", trigger["id"], period="monthly", hard_limit_usd=0.01)

    # Create a prior execution with usage exceeding the hard limit
    create_execution_log(
        execution_id="exec-prev-direct",
        trigger_id=trigger["id"],
        trigger_type="manual",
        started_at=datetime.datetime.now().isoformat(),
        prompt="test",
        backend_type="claude",
        command="test",
    )
    create_token_usage_record(
        execution_id="exec-prev-direct",
        entity_type="trigger",
        entity_id=trigger["id"],
        backend_type="claude",
        account_id=None,
        input_tokens=500,
        output_tokens=1000,
        total_cost_usd=0.05,  # exceeds $0.01 hard limit
    )

    # Mock get_paths_for_trigger_detailed to return empty paths
    monkeypatch.setattr(
        "app.services.execution_service.get_paths_for_trigger_detailed",
        lambda trigger_id: [],
    )

    # Track if subprocess.Popen is called (it should NOT be)
    popen_called = []

    def mock_popen(*args, **kwargs):
        popen_called.append(True)
        return _make_mock_process(["test"])

    monkeypatch.setattr("subprocess.Popen", mock_popen)

    # Mock ProcessManager
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.register",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.is_cancelled",
        lambda *a, **kw: False,
    )
    monkeypatch.setattr(
        "app.services.execution_service.ProcessManager.cleanup",
        lambda *a, **kw: None,
    )

    execution_id = ExecutionService.run_trigger(
        trigger, "test message", trigger_type="manual", account_id=None
    )

    assert execution_id is not None, "run_trigger should return an execution_id even when blocked"
    assert len(popen_called) == 0, "subprocess.Popen should NOT have been called"

    # Verify the execution was marked as failed
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT status, error_message FROM execution_logs WHERE execution_id = ?",
            (execution_id,),
        )
        row = cursor.fetchone()

    assert row is not None
    assert row["status"] == "failed"
    assert "Budget limit exceeded" in row["error_message"]
