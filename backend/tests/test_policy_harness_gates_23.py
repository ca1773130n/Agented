"""Phase 23 — fourth fix round: fail-CLOSED policy gate + harness-launch coverage.

Covers the four merge-blocking fixes plus the additional AI-harness spawns found
in the exhaustive re-audit:

1. FAIL CLOSED on a policy-store DB error (``evaluate`` / ``enforce_launch`` /
   ``enforce_launch_noninteractive`` all deny, never allow).
2. topology_strategies generator-critic oracle check routes through the gate.
3. the one-shot harness launches (base_generation, skill_testing, backend_test,
   team_generation, replay) are gated BEFORE any spawn.
4. no orphan decision-tuple leak after a timed-out / never-awaited ASK.
"""

import io
import sqlite3

import pytest

from app.services.policy_service import PolicyDenied, PolicyService


def _seed(scope, scope_id, effect, *, kind="manual", priority=0, params=None):
    return PolicyService.create_policy(
        scope=scope, scope_id=scope_id, kind=kind, effect=effect, priority=priority, params=params
    )


def _no_popen(*a, **k):
    raise AssertionError("subprocess spawn must NOT happen when the launch is policy-blocked")


class _FakeProc:
    """Minimal Popen stand-in: empty streams, clean exit."""

    def __init__(self, *a, **k):
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
        self.returncode = 0

    def wait(self, *a, **k):
        return 0

    def kill(self):
        pass


# --------------------------------------------------------------------------- #
# FIX 1 — fail CLOSED on a policy-lookup DB error                             #
# --------------------------------------------------------------------------- #


def _patch_rows_raise(monkeypatch):
    def _raise_op(*a, **k):
        raise sqlite3.OperationalError("simulated policy store failure")

    monkeypatch.setattr(PolicyService, "_rows_for", _raise_op)


def test_evaluate_fails_closed_on_db_error(isolated_db, monkeypatch):
    _patch_rows_raise(monkeypatch)
    verdict = PolicyService.evaluate(session_id="s1", action={"kind": "process_launch"})
    assert verdict["decision"] == "deny", "a DB error must yield a DENY verdict, never allow"


def test_enforce_launch_denies_on_db_error(isolated_db, monkeypatch):
    _patch_rows_raise(monkeypatch)
    with pytest.raises(PolicyDenied):
        PolicyService.enforce_launch(session_id="s2", cmd=["claude", "-p", "x"], backend="claude")


def test_enforce_launch_noninteractive_denies_on_db_error(isolated_db, monkeypatch):
    _patch_rows_raise(monkeypatch)
    with pytest.raises(PolicyDenied):
        PolicyService.enforce_launch_noninteractive(
            session_id="s3", cmd=["claude", "-p", "x"], backend="claude"
        )


# --------------------------------------------------------------------------- #
# FIX 4 — no orphan decision-tuple leak                                        #
# --------------------------------------------------------------------------- #


def _stub_psm(monkeypatch):
    from app.services.project_session_manager import ProjectSessionManager

    monkeypatch.setattr(
        ProjectSessionManager, "register_and_broadcast_policy_ask", lambda *a, **k: None
    )
    monkeypatch.setattr(ProjectSessionManager, "clear_pending_policy_ask", lambda *a, **k: None)
    monkeypatch.setattr(ProjectSessionManager, "_broadcast", lambda *a, **k: None)


def test_submit_before_await_is_stored_and_consumed(isolated_db, monkeypatch):
    """A decision racing AHEAD of its await (same ask_id) must be STORED, not
    dropped, so the later await picks it up — preserving the launch-ASK race fix
    (FIX 4 must not regress this)."""
    _stub_psm(monkeypatch)
    aid = "ask-race-ahead"
    pending = PolicyService.submit_policy_decision("s", "approve", ask_id=aid)
    assert pending is False, "no waiter was registered when the decision arrived"
    decision = PolicyService.await_decision(
        "s", {"decision": "ask"}, ask_id=aid, max_wall_seconds=2
    )
    assert decision == "approve", "a decision racing ahead of the await must not be lost"


def test_orphan_decision_evicted_by_ttl(isolated_db, monkeypatch):
    """FIX 4: a late/stray decision consumed by NOBODY (its await already timed
    out) must not leak — the TTL sweep on the next submit evicts it so the
    registry stays bounded."""
    from app.services import policy_service as ps

    _stub_psm(monkeypatch)
    monkeypatch.setattr(ps, "_POLICY_DECISION_TTL_SECONDS", 0)  # every stored tuple instantly stale

    aid = "ask-timeout-1"
    assert (
        PolicyService.await_decision("s", {"policy_id": "p"}, ask_id=aid, max_wall_seconds=0)
        == "deny"
    )
    assert aid not in ps._POLICY_DECISIONS, "the waiter's finally pops its own sentinel"

    # Late operator decision arrives AFTER the wait gave up → stores an orphan.
    PolicyService.submit_policy_decision("s", "approve", ask_id=aid)
    # The NEXT submit's TTL sweep (TTL=0) evicts the now-stale orphan.
    PolicyService.submit_policy_decision("s", "approve", ask_id="ask-unrelated")
    assert aid not in ps._POLICY_DECISIONS, "orphan tuple evicted — no unbounded leak"


# --------------------------------------------------------------------------- #
# FIX 2 — topology_strategies generator-critic oracle check is gated          #
# --------------------------------------------------------------------------- #


def _run_agent_stub(calls):
    def run_agent(team, agent_id, message, event, trigger_type, working_directory):
        calls.append((agent_id, message))
        return (f"eid-{len(calls)}", "generator output (no APPROVED token)")

    return run_agent


def test_generator_critic_deny_skips_oracle_check(isolated_db, monkeypatch):
    from app.services import topology_strategies

    _seed("server", None, "deny", kind="manual")

    called = {"n": 0}

    def _fake_check(*a, **k):
        called["n"] += 1
        raise AssertionError("run_isolated_check must NOT run when policy denies")

    monkeypatch.setattr("app.services.sandbox_eval.run_isolated_check", _fake_check)

    calls = []
    ids = topology_strategies.execute_generator_critic(
        {"id": "t"},
        {"generator": "g", "critic": "c", "check_cmd": "true", "max_iterations": 1},
        "build it",
        {},
        "manual",
        "/tmp",
        run_agent=_run_agent_stub(calls),
    )
    assert called["n"] == 0, "the oracle check must be blocked before any spawn"
    assert len(ids) == 2, "the loop still runs generator+critic, falling back to the critic gate"


# --------------------------------------------------------------------------- #
# FIX 3 — one-shot harness launches gated before spawn                         #
# --------------------------------------------------------------------------- #


class _StubGen:
    """Concrete BaseGenerationService for the streaming-generation gate test."""

    @classmethod
    def _make(cls):
        from app.services.base_generation_service import BaseGenerationService

        class _G(BaseGenerationService):
            @classmethod
            def _gather_context(cls):
                return {}

            @classmethod
            def _build_prompt(cls, description, context):
                return "do it"

            @classmethod
            def _extract_progress(cls, text, reported):
                return []

            @classmethod
            def _validate(cls, config):
                return (config, [])

        return _G


def test_base_generation_deny_blocks_popen(isolated_db, monkeypatch):
    import app.services.base_generation_service as bg

    _seed("server", None, "deny", kind="manual")
    monkeypatch.setattr(bg.subprocess, "Popen", _no_popen)

    events = list(_StubGen._make().generate_streaming("x"))
    assert any("policy" in e.lower() for e in events), "deny must surface a policy error event"


def test_base_generation_allow_calls_popen(isolated_db, monkeypatch):
    import app.services.base_generation_service as bg

    calls = {"n": 0}

    def _fake_popen(*a, **k):
        calls["n"] += 1
        return _FakeProc()

    monkeypatch.setattr(bg.subprocess, "Popen", _fake_popen)
    list(_StubGen._make().generate_streaming("x"))
    assert calls["n"] == 1, "default-allow must proceed to the Popen"


def test_skill_testing_deny_blocks_popen(isolated_db, monkeypatch, tmp_path):
    import app.services.skill_testing_service as st
    from app.services.skill_testing_service import SkillTestingService as S

    _seed("server", None, "deny", kind="manual")
    monkeypatch.setattr(st.subprocess, "Popen", _no_popen)
    monkeypatch.setattr(st, "get_playground_working_dir", lambda: str(tmp_path))

    tid = "skill-deny"
    with S._lock:
        S._test_sessions[tid] = {"status": "running", "skill_name": "x", "output": []}
        S._test_subscribers[tid] = []
    S._run_skill_test(tid, "myskill", "")
    assert S._test_sessions[tid]["status"] == "failed"


def test_skill_testing_allow_calls_popen(isolated_db, monkeypatch, tmp_path):
    import app.services.skill_testing_service as st
    from app.services.skill_testing_service import SkillTestingService as S

    calls = {"n": 0}

    def _fake_popen(*a, **k):
        calls["n"] += 1
        return _FakeProc()

    monkeypatch.setattr(st.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(st, "get_playground_working_dir", lambda: str(tmp_path))

    tid = "skill-allow"
    with S._lock:
        S._test_sessions[tid] = {"status": "running", "skill_name": "x", "output": []}
        S._test_subscribers[tid] = []
    S._run_skill_test(tid, "myskill", "")
    assert calls["n"] == 1


def test_backend_test_cli_deny_blocks_popen(isolated_db, monkeypatch):
    import app.services.backend_test_service as bt
    from app.services.backend_test_service import BackendTestService as B

    _seed("server", None, "deny", kind="manual")
    monkeypatch.setattr(bt.subprocess, "Popen", _no_popen)

    tid = "bt-deny"
    with B._lock:
        B._test_sessions[tid] = {"status": "running", "output": []}
        B._test_subscribers[tid] = []
    B._run_test_via_cli(tid, "opencode", "hi", None, None)
    assert B._test_sessions[tid]["status"] == "failed"


def test_backend_test_cli_allow_calls_popen(isolated_db, monkeypatch):
    import app.services.backend_test_service as bt
    from app.services.backend_test_service import BackendTestService as B

    calls = {"n": 0}

    def _fake_popen(*a, **k):
        calls["n"] += 1
        return _FakeProc()

    monkeypatch.setattr(bt.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr("app.services.skills_service.get_playground_working_dir", lambda: "/tmp")

    tid = "bt-allow"
    with B._lock:
        B._test_sessions[tid] = {"status": "running", "output": []}
        B._test_subscribers[tid] = []
    B._run_test_via_cli(tid, "opencode", "hi", None, None)
    assert calls["n"] == 1


def test_team_generation_deny_blocks_run(isolated_db, monkeypatch):
    import app.services.team_generation_service as tg
    from app.services.team_generation_service import TeamGenerationService as T

    _seed("server", None, "deny", kind="manual")

    def _no_run(*a, **k):
        raise AssertionError("subprocess.run must not run on deny")

    monkeypatch.setattr(tg.subprocess, "run", _no_run)
    monkeypatch.setattr(T, "_gather_context", classmethod(lambda cls: {}))
    monkeypatch.setattr(T, "_build_prompt", classmethod(lambda cls, d, c: "p"))

    with pytest.raises(RuntimeError) as exc:
        T.generate("desc")
    assert "policy" in str(exc.value).lower()


def test_team_generation_allow_calls_run(isolated_db, monkeypatch):
    import app.services.team_generation_service as tg
    from app.services.team_generation_service import TeamGenerationService as T

    calls = {"n": 0}

    class _R:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def _fake_run(*a, **k):
        calls["n"] += 1
        return _R()

    monkeypatch.setattr(tg.subprocess, "run", _fake_run)
    monkeypatch.setattr(T, "_gather_context", classmethod(lambda cls: {}))
    monkeypatch.setattr(T, "_build_prompt", classmethod(lambda cls, d, c: "p"))
    monkeypatch.setattr(T, "_validate", classmethod(lambda cls, config: (config, [])))

    T.generate("desc")
    assert calls["n"] == 1


def test_replay_deny_blocks_popen(isolated_db, monkeypatch):
    import app.services.replay_service as rp
    from app.services.replay_service import ReplayService as R

    _seed("server", None, "deny", kind="manual")
    monkeypatch.setattr(rp.subprocess, "Popen", _no_popen)

    finished = {}
    monkeypatch.setattr(rp.ExecutionLogService, "finish_execution", lambda **k: finished.update(k))

    R._run_replay_subprocess("ex-1", "claude -p hi", "trig-1", "claude")
    assert finished.get("status") == "failed"
    assert "policy" in (finished.get("error_message", "").lower())


def test_model_discovery_claude_probe_deny_skips_run(isolated_db, monkeypatch):
    # round-5: the `claude -p` model-discovery probe must be gated like the gemini one.
    import shutil

    import app.services.model_discovery_service as md
    from app.services.model_discovery_service import ModelDiscoveryService as M

    _seed("server", None, "deny", kind="manual")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/claude")

    def _no_run(*a, **k):
        raise AssertionError("claude discovery probe must not run subprocess on deny")

    monkeypatch.setattr(md.subprocess, "run", _no_run)
    # deny short-circuits every _probe before subprocess.run → no probe runs, result None.
    assert M._discover_claude_models_pty() is None
