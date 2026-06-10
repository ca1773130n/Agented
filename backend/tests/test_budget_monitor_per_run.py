"""Per-run budget tick: accounting, one-shot warn, hard kill (Phase 3 P6)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.db import harness_state
from app.db.budgets import set_budget_limit
from app.services.budget_service import BudgetService
from app.services.execution_runner import _per_run_budget_tick, budget_monitor


def _make_execution(execution_id: str = "exec-1", trigger_id: str = "bot-pr-review") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id=trigger_id,
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="codex",
        command="echo hi",
    )


def _fake_process() -> SimpleNamespace:
    return SimpleNamespace(pid=99999)


def _usage(cost: float) -> dict:
    return {"input_tokens": 10, "output_tokens": 5, "total_cost_usd": cost}


def _tick(execution_id: str, state: dict, cost: float) -> None:
    with patch.object(BudgetService, "extract_token_usage", return_value=_usage(cost)):
        _per_run_budget_tick(
            execution_id,
            "bot-pr-review",
            "trigger",
            "bot-pr-review",
            "codex",
            _fake_process(),
            state,
        )


def test_tick_updates_budget_used_without_limit():
    _make_execution()
    state = {}
    _tick("exec-1", state, 0.10)
    assert harness_state.get_run("exec-1")["budget_used"] == pytest.approx(0.10)
    assert not state.get("warned") and not state.get("killed")


def test_tick_noop_when_extraction_returns_none():
    """claude/gemini mid-run: extraction yields None -> documented no-op."""
    _make_execution()
    with patch.object(BudgetService, "extract_token_usage", return_value=None):
        _per_run_budget_tick(
            "exec-1",
            "bot-pr-review",
            "trigger",
            "bot-pr-review",
            "claude",
            _fake_process(),
            {},
        )
    assert harness_state.get_run("exec-1") is None  # nothing written


def test_tick_warns_once_at_80_percent():
    _make_execution()
    set_budget_limit("trigger", "bot-pr-review", per_run_limit_usd=1.0)
    state = {}
    with patch("app.services.execution_log_service.ExecutionLogService.append_log") as append:
        _tick("exec-1", state, 0.85)
        _tick("exec-1", state, 0.90)  # second tick must NOT warn again
    warn_calls = [c for c in append.call_args_list if "[BUDGET]" in str(c)]
    assert len(warn_calls) == 1
    assert state.get("warned") is True
    assert not state.get("killed")


def test_tick_kills_at_limit():
    _make_execution()
    set_budget_limit("trigger", "bot-pr-review", per_run_limit_usd=1.0)
    state = {}
    with patch("os.killpg") as killpg, patch("os.getpgid", return_value=4242):
        _tick("exec-1", state, 1.2)
    killpg.assert_called_once()
    assert state.get("killed") is True


def test_tick_no_enforcement_when_limit_null():
    _make_execution()
    set_budget_limit("trigger", "bot-pr-review", hard_limit_usd=100.0)  # per_run stays NULL
    state = {}
    with patch("os.killpg") as killpg:
        _tick("exec-1", state, 50.0)
    killpg.assert_not_called()
    assert not state.get("warned") and not state.get("killed")


def test_tick_fails_open_on_parser_error():
    _make_execution()
    with patch.object(BudgetService, "extract_token_usage", side_effect=RuntimeError("boom")):
        # Must not raise — the monitor's period check must never be disrupted.
        _per_run_budget_tick(
            "exec-1",
            "bot-pr-review",
            "trigger",
            "bot-pr-review",
            "codex",
            _fake_process(),
            {},
        )


def test_budget_monitor_invokes_tick():
    """Wiring: the polling loop calls the tick with the threaded backend_type."""
    _make_execution()
    process = MagicMock()
    # Loop order is poll -> sleep -> poll-again -> tick, so one live tick
    # needs TWO None polls before the terminal 0.
    process.poll.side_effect = [None, None, 0]
    with (
        patch("app.services.execution_runner._per_run_budget_tick") as tick,
        patch.object(BudgetService, "check_budget", return_value={"allowed": True}),
        patch.object(BudgetService, "check_execution_time_limit", return_value=False),
    ):
        budget_monitor(
            "exec-1",
            "bot-pr-review",
            "trigger",
            "bot-pr-review",
            process,
            interval_seconds=0,
            backend_type="codex",
        )
    assert tick.call_count == 1
    assert tick.call_args[0][4] == "codex"  # backend_type positional
