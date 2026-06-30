"""Builtin policy evaluators — per-evaluator unit tests (phase 23, 23-02, SC2).

The four builtins (cost_budget, max_tool_calls_per_session, ask_on_os_tools,
enforce_sandbox) are PURE functions: they take a policy ``row`` (carrying its
parsed ``params`` dict) plus an ``action`` ctx dict and return ``(decision,
reason)``. No DB is touched here — the evaluators are exercised directly so the
case tables are trivially verifiable. ``enforce_sandbox`` is INERT until Phase
24 (it produces a verdict but invokes no sandbox); the inert path is asserted.

A final block routes a cost_budget row through ``PolicyService._eval_row`` to
prove the ``_BUILTINS`` dispatch wires the pure evaluator into the 23-01 stack.
"""

from app.services.policy_service import (
    PolicyService,
    _BUILTINS,
    _eval_ask_on_os_tools,
    _eval_cost_budget,
    _eval_enforce_sandbox,
    _eval_max_tool_calls,
)


def _row(kind, params):
    return {"id": "pol-test1", "kind": kind, "effect": "ask", "params": params}


# -- cost_budget ----------------------------------------------------------


def test_cost_budget_allows_when_spend_below_soft():
    row = _row("cost_budget", {"max_cost_usd": 10.0, "ask_thresholds_usd": [5.0]})
    decision, _ = _eval_cost_budget(row, {"total_cost_usd": 0.0})
    assert decision == "allow"


def test_cost_budget_asks_when_crossing_soft_threshold():
    row = _row("cost_budget", {"max_cost_usd": 10.0, "ask_thresholds_usd": [5.0]})
    decision, reason = _eval_cost_budget(row, {"total_cost_usd": 6.0})
    assert decision == "ask"
    assert "threshold" in reason.lower()


def test_cost_budget_denies_at_or_above_hard_cap():
    row = _row("cost_budget", {"max_cost_usd": 10.0, "ask_thresholds_usd": [5.0]})
    decision, reason = _eval_cost_budget(row, {"total_cost_usd": 12.0})
    assert decision == "deny"
    assert "cost" in reason.lower()


def test_cost_budget_falls_back_to_spend_key():
    row = _row("cost_budget", {"max_cost_usd": 10.0, "ask_thresholds_usd": [5.0]})
    decision, _ = _eval_cost_budget(row, {"spend": 6.0})
    assert decision == "ask"


def test_cost_budget_zero_cap_does_not_deny():
    # max_cost_usd <= 0 disables the hard cap.
    row = _row("cost_budget", {"max_cost_usd": 0, "ask_thresholds_usd": []})
    decision, _ = _eval_cost_budget(row, {"total_cost_usd": 999.0})
    assert decision == "allow"


# -- max_tool_calls_per_session -------------------------------------------


def test_max_tool_calls_allows_under_limit():
    row = _row("max_tool_calls_per_session", {"max_tool_calls": 5})
    decision, _ = _eval_max_tool_calls(row, {"tool_calls": 3})
    assert decision == "allow"


def test_max_tool_calls_denies_at_limit():
    row = _row("max_tool_calls_per_session", {"max_tool_calls": 5})
    decision, reason = _eval_max_tool_calls(row, {"tool_calls": 5})
    assert decision == "deny"
    assert "tool-call" in reason.lower()


def test_max_tool_calls_zero_limit_does_not_deny():
    row = _row("max_tool_calls_per_session", {"max_tool_calls": 0})
    decision, _ = _eval_max_tool_calls(row, {"tool_calls": 100})
    assert decision == "allow"


# -- ask_on_os_tools ------------------------------------------------------


def test_ask_on_os_tools_asks_for_shell():
    row = _row("ask_on_os_tools", {})
    decision, reason = _eval_ask_on_os_tools(row, {"kind": "shell"})
    assert decision == "ask"
    assert "shell" in reason.lower()


def test_ask_on_os_tools_allows_read():
    row = _row("ask_on_os_tools", {})
    decision, _ = _eval_ask_on_os_tools(row, {"kind": "read"})
    assert decision == "allow"


def test_ask_on_os_tools_honors_custom_kinds():
    row = _row("ask_on_os_tools", {"kinds": ["network"]})
    assert _eval_ask_on_os_tools(row, {"kind": "network"})[0] == "ask"
    # shell is no longer in the custom kinds set -> allow.
    assert _eval_ask_on_os_tools(row, {"kind": "shell"})[0] == "allow"


# -- enforce_sandbox (INERT until Phase 24) -------------------------------


def test_enforce_sandbox_denies_non_sandboxed_launch():
    row = _row("enforce_sandbox", {"require_sandbox": True})
    decision, reason = _eval_enforce_sandbox(
        row, {"kind": "process_launch", "sandboxed": False}
    )
    assert decision == "deny"
    assert "sandbox" in reason.lower()


def test_enforce_sandbox_allows_sandboxed_launch():
    row = _row("enforce_sandbox", {"require_sandbox": True})
    decision, _ = _eval_enforce_sandbox(
        row, {"kind": "process_launch", "sandboxed": True}
    )
    assert decision == "allow"


def test_enforce_sandbox_inert_for_non_launch_action():
    row = _row("enforce_sandbox", {"require_sandbox": True})
    decision, reason = _eval_enforce_sandbox(row, {"kind": "read", "sandboxed": False})
    assert decision == "allow"
    assert "inert" in reason.lower()


# -- dispatch wiring ------------------------------------------------------


def test_builtins_dispatch_registers_all_four():
    assert set(_BUILTINS) == {
        "cost_budget",
        "max_tool_calls_per_session",
        "ask_on_os_tools",
        "enforce_sandbox",
    }


def test_eval_row_routes_cost_budget_through_builtin():
    row = _row("cost_budget", {"max_cost_usd": 10.0, "ask_thresholds_usd": [5.0]})
    decision, _ = PolicyService._eval_row(row, {"total_cost_usd": 12.0})
    assert decision == "deny"


def test_eval_row_falls_back_to_effect_for_unknown_kind():
    row = {"id": "pol-xx", "kind": "custom", "effect": "ask", "params": {}}
    decision, _ = PolicyService._eval_row(row, {})
    assert decision == "ask"
