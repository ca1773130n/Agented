"""Token->USD conversion + live budget_used upsert (Harness-1 Phase 3, P6)."""

import pytest

from app.db import harness_state
from app.services.budget_service import BudgetService


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


def test_native_cost_passthrough():
    usage = {"input_tokens": 100, "output_tokens": 50, "total_cost_usd": 0.42}
    assert BudgetService.cost_from_usage(usage, "claude") == pytest.approx(0.42)


def test_zero_native_cost_estimates_with_codex_pricing():
    """codex extraction reports total_cost_usd=0.0 — must estimate using CODEX
    pricing (session_cost_service), NOT the claude fallback rate."""
    from app.services.session_cost_service import _PRICING

    usage = {"input_tokens": 1_000_000, "output_tokens": 0, "total_cost_usd": 0.0}
    cost = BudgetService.cost_from_usage(usage, "codex")
    assert cost == pytest.approx(_PRICING["gpt-5.3-codex"]["input"])
    # And claude-backend estimates use claude rates (when no native cost).
    cost_claude = BudgetService.cost_from_usage(usage, "claude")
    assert cost_claude == pytest.approx(_PRICING["claude-sonnet-4"]["input"])


def test_none_usage_is_zero():
    assert BudgetService.cost_from_usage(None, "codex") == 0.0
    assert BudgetService.cost_from_usage({}, "codex") == 0.0


def test_update_budget_used_upserts_run_row():
    _make_execution()
    harness_state.update_budget_used("exec-1", 0.10)  # creates the run row
    assert harness_state.get_run("exec-1")["budget_used"] == pytest.approx(0.10)
    harness_state.update_budget_used("exec-1", 0.25)  # updates in place
    run = harness_state.get_run("exec-1")
    assert run["budget_used"] == pytest.approx(0.25)
    assert run["step_cursor"] == 0  # accounting must not advance the checkpoint cursor


def test_update_budget_used_is_monotonic():
    """Live cost only grows; a stale lower write (e.g. racing a checkpoint)
    must not regress the recorded value."""
    _make_execution()
    harness_state.update_budget_used("exec-1", 0.25)
    harness_state.update_budget_used("exec-1", 0.10)  # stale — ignored by MAX
    assert harness_state.get_run("exec-1")["budget_used"] == pytest.approx(0.25)


def test_count_checkpoints():
    _make_execution()
    assert harness_state.count_checkpoints("exec-1") == 0
    harness_state.record_checkpoint("exec-1", ledger={"lines": []})
    harness_state.record_checkpoint("exec-1", ledger={"lines": []})
    assert harness_state.count_checkpoints("exec-1") == 2
