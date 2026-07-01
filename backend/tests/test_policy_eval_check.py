"""FIX 1 (23 BLOCKER) — the goal-judge deterministic eval-check launch gate.

``GoalJudgeService._run_deterministic`` spawns an operator ``check_cmd`` via
``subprocess.Popen(shell=True)`` (in ``sandbox_eval``). That is an autonomous,
unattended launch and was the one autonomous spawn path that did NOT clear the
stackable policy layer. It now routes through
``PolicyService.enforce_launch_noninteractive`` BEFORE anything is spawned.

A deterministic eval check is fire-and-forget grading machinery, so the gate is
NON-interactive: a DENY refuses to run the check, and an ASK is ALSO treated as a
refusal (there is no human turn to prompt) — both fail CLOSED without spawning.
"""

import pytest


def _seed(scope, scope_id, effect, *, kind="manual", priority=0, params=None):
    from app.services.policy_service import PolicyService

    return PolicyService.create_policy(
        scope=scope,
        scope_id=scope_id,
        kind=kind,
        effect=effect,
        priority=priority,
        params=params,
    )


def _popen_spy(monkeypatch):
    """Patch sandbox_eval's Popen with a counter that fails if ever called."""
    from app.services import sandbox_eval as se_mod

    calls = {"n": 0}

    def _fake_popen(*a, **k):
        calls["n"] += 1
        raise AssertionError("subprocess.Popen must NOT be called when the check is policy-blocked")

    monkeypatch.setattr(se_mod.subprocess, "Popen", _fake_popen)
    return calls


# ---------------------------------------------------------------------------
# End-to-end through GoalJudgeService.judge (the real call path)
# ---------------------------------------------------------------------------


def test_deny_blocks_eval_check_subprocess(isolated_db, monkeypatch):
    """A server-scope DENY blocks the deterministic check: no Popen, not-met."""
    from app.services.goal_judge_service import GoalJudgeService

    _seed("server", None, "deny", kind="manual")
    calls = _popen_spy(monkeypatch)

    verdict = GoalJudgeService.judge("goal", "turn", check_cmd="true", session_id="sess-deny-check")

    assert calls["n"] == 0, "the check subprocess must never spawn under a DENY policy"
    assert verdict.met is False
    assert verdict.source == "deterministic"
    assert "policy blocked" in verdict.reason


def test_ask_also_refuses_eval_check_non_interactively(isolated_db, monkeypatch):
    """An ASK is not interactively approvable for a fire-and-forget check — it is
    treated as a refusal (fail closed), never blocking on a human, no Popen."""
    from app.services.goal_judge_service import GoalJudgeService

    # ask_on_os_tools → a process_launch action yields an ASK verdict.
    _seed("session", "sess-ask-check", "ask", kind="ask_on_os_tools")
    calls = _popen_spy(monkeypatch)

    verdict = GoalJudgeService.judge("goal", "turn", check_cmd="true", session_id="sess-ask-check")

    assert calls["n"] == 0, "an ASK check must not spawn — no human prompt for a check"
    assert verdict.met is False
    assert "policy blocked" in verdict.reason


def test_default_allow_runs_eval_check(isolated_db, tmp_path):
    """No matching policy → default ALLOW → the check actually runs (exit 0 → met).
    Uses an empty tmp cwd so the isolated snapshot is cheap."""
    from app.services.goal_judge_service import GoalJudgeService

    verdict = GoalJudgeService.judge(
        "goal",
        "turn",
        check_cmd="true",
        cwd=str(tmp_path),
        session_id="sess-allow-check",
    )
    assert verdict.met is True, "default-allow must let the check run and pass"
    assert verdict.source == "deterministic"


# ---------------------------------------------------------------------------
# enforce_launch_noninteractive unit semantics (allow/deny/ask mapping)
# ---------------------------------------------------------------------------


def test_noninteractive_gate_allow_returns(isolated_db):
    from app.services.policy_service import PolicyService

    # No policy → allow → returns without raising.
    PolicyService.enforce_launch_noninteractive(
        session_id="sess-ni-allow",
        cmd=["/bin/sh", "-c", "true"],
        backend="goal-judge-check",
    )


def test_noninteractive_gate_deny_raises(isolated_db):
    from app.services.policy_service import PolicyDenied, PolicyService

    _seed("server", None, "deny", kind="manual")
    with pytest.raises(PolicyDenied):
        PolicyService.enforce_launch_noninteractive(
            session_id="sess-ni-deny",
            cmd=["/bin/sh", "-c", "true"],
            backend="goal-judge-check",
        )


def test_noninteractive_gate_ask_raises_not_blocks(isolated_db):
    """ASK must RAISE PolicyDenied immediately (fail closed), NOT block on a human."""
    from app.services.policy_service import PolicyDenied, PolicyService

    _seed("session", "sess-ni-ask", "ask", kind="ask_on_os_tools")
    with pytest.raises(PolicyDenied) as exc:
        PolicyService.enforce_launch_noninteractive(
            session_id="sess-ni-ask",
            cmd=["/bin/sh", "-c", "true"],
            backend="goal-judge-check",
        )
    assert "requires approval" in str(exc.value)


def test_noninteractive_gate_enforce_sandbox_denies_inherit_allows_isolated(isolated_db):
    """The ``enforce_sandbox`` builtin denies a NON-sandboxed launch and allows a
    sandboxed one — so the goal-judge inherit escape hatch (sandboxed=False) is
    blocked while the default isolated path (sandboxed=True) runs."""
    from app.services.policy_service import PolicyDenied, PolicyService

    _seed("server", None, "deny", kind="enforce_sandbox", params={"require_sandbox": True})

    # inherit path: not sandboxed → denied.
    with pytest.raises(PolicyDenied):
        PolicyService.enforce_launch_noninteractive(
            session_id="sess-sbx",
            cmd=["/bin/sh", "-c", "true"],
            backend="goal-judge-check",
            sandboxed=False,
        )

    # isolated path: sandboxed → allowed (returns).
    PolicyService.enforce_launch_noninteractive(
        session_id="sess-sbx",
        cmd=["/bin/sh", "-c", "true"],
        backend="goal-judge-check",
        sandboxed=True,
    )
