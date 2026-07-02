# 23-03 SUMMARY — policy enforcement at the Popen boundary + ASK await

**Status:** DONE. `policy_service.py` (await/decision helpers), `execution_service.py`, `goal_loop_runner.py` + `tests/test_policy_enforcement.py` (now 21 tests, green). Commits `abc9a6920e`, `675b820c76`.

- `await_decision(session_id, verdict, *, max_wall_seconds=600) -> str`: broadcasts `policy_ask` over the EXISTING `ProjectSessionManager._broadcast` SSE primitive (no new transport, 23-RESEARCH Rec 1), polls a session-keyed registry, emits `policy_ask_resolved`, and fails closed to `"deny"` on timeout.
- `submit_policy_decision(session_id, decision, message=None) -> bool`: resolver mirroring `goal_loop_runner.submit_gate_decision`.
- `ExecutionService._enforce_launch_policy`: `PolicyService.evaluate` runs AFTER cmd/proc_env build, BEFORE `subprocess.Popen` (Pitfall 1 — never blocks stream readers); DENY raises `PolicyDenied` (no launch), ASK blocks via `await_decision` (approve proceeds, else raises). `run_trigger` catches `PolicyDenied` → clean FAILED. Session-scoped (`AGENTED_SESSION_ID`, fallback `execution_id`); a bot/trigger id is never a policy key.
- `goal_loop_runner`: the exit-ladder cost cap now routes through `_evaluate_cost_policy` (the `cost_budget` builtin is the single source of truth), ASK routes through the existing `_await_gate`, and predefined safety bots delegate to the one session-scoped launch gate — no parallel poll loop (Pitfall 5). Implicit `spec.max_cost_usd` ceiling kept for back-compat.
- `policy_ask` payload = `{policy_id, kind, reason, scope}` (the contract 23-04/23-05 consume; `ask_id` added later in round-3 hardening).

Later phase-23 codex-hardening rounds fortified this (fail-closed on DB error, `ask_id`-scoped decisions, TTL registry sweep), growing `test_policy_enforcement.py` to 21 tests.
