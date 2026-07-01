"""Enforce-AFTER-wrap wiring proof (24-fix, crit 4-9).

Every previously-unwired harness launch site now routes through the shared
``sandbox_wrap.apply_sandbox_and_enforce`` seam: wrap FIRST, compute the REAL
``sandboxed`` flag, THEN run the Phase-23 launch gate — BEFORE any spawn. With a
seeded ``enforce_sandbox`` DENY policy and a degraded (``sandboxed=False``) wrap,
each path must REFUSE the launch and never reach ``subprocess.Popen`` / ``os.fork``.

Fail-CLOSED is the property under test; the wrap itself is monkeypatched to the
degraded ``(cmd, False)`` return so the assertion holds identically on every host
(no real bwrap/seatbelt needed).
"""

import subprocess

import pytest

from app.services import sandbox_wrap
from app.services.policy_service import PolicyDenied, PolicyService


def _seed_enforce_sandbox_deny():
    PolicyService.create_policy(
        scope="server",
        scope_id=None,
        kind="enforce_sandbox",
        effect="deny",
        params={"require_sandbox": True},
        priority=100,
    )


@pytest.fixture
def deny_and_degrade(isolated_db, monkeypatch):
    """Seed a require-sandbox DENY + force the wrap to degrade to sandboxed=False,
    and install Popen/fork sentinels that FAIL if a spawn is ever reached."""
    _seed_enforce_sandbox_deny()
    monkeypatch.setattr(
        sandbox_wrap, "wrap_harness_command", lambda cmd, ws, **k: (list(cmd), False)
    )

    def _no_popen(*a, **k):  # pragma: no cover - asserted not to run
        raise AssertionError("subprocess.Popen must not run when the launch is refused")

    monkeypatch.setattr(subprocess, "Popen", _no_popen)
    return monkeypatch


# --------------------------------------------------------------------------- #
# The shared seam itself (interactive + non-interactive).
# --------------------------------------------------------------------------- #
def test_shared_helper_noninteractive_refuses(deny_and_degrade):
    with pytest.raises(PolicyDenied):
        sandbox_wrap.apply_sandbox_and_enforce(
            ["claude", "-p", "x"], "/ws", session_id="", backend="claude"
        )


def test_shared_helper_interactive_refuses(deny_and_degrade):
    with pytest.raises(PolicyDenied):
        sandbox_wrap.apply_sandbox_and_enforce(
            ["claude", "-p", "x"], "/ws", session_id="", backend="claude", interactive=True
        )


def test_shared_helper_sandboxed_proceeds(isolated_db, monkeypatch):
    """A real sandbox (sandboxed=True) satisfies the require-sandbox policy — the
    launch proceeds (the enforce-after-wrap ordering fix for MAJORS 8-9)."""
    _seed_enforce_sandbox_deny()
    monkeypatch.setattr(
        sandbox_wrap, "wrap_harness_command", lambda cmd, ws, **k: (["bwrap", "--", *cmd], True)
    )
    wrapped, sandboxed = sandbox_wrap.apply_sandbox_and_enforce(
        ["claude", "-p", "x"], "/ws", session_id="", backend="claude"
    )
    assert sandboxed is True
    assert wrapped[0] == "bwrap"


# --------------------------------------------------------------------------- #
# crit 4 — setup_execution_service.start_setup
# --------------------------------------------------------------------------- #
def test_setup_execution_refused(deny_and_degrade):
    from app.services.setup_execution_service import SetupExecutionService

    with pytest.raises(PolicyDenied):
        SetupExecutionService.start_setup("proj-x", "claude -p hi", working_dir="/ws")


# --------------------------------------------------------------------------- #
# crit 5 — cli_agent_runner_service._run_subprocess (generator)
# --------------------------------------------------------------------------- #
def test_cli_agent_refused(deny_and_degrade):
    from app.services import cli_agent_runner_service as cli

    out = list(
        cli._run_subprocess(
            ["claude", "-p", "x"],
            cwd="/ws",
            line_handler=lambda line: line,
            backend_label="claude",
        )
    )
    assert any("blocked by policy" in o for o in out), out


# --------------------------------------------------------------------------- #
# crit 6 — conversation_streaming CLI fallback + OpenCode (generators)
# --------------------------------------------------------------------------- #
def test_conversation_cli_fallback_refused(deny_and_degrade):
    from app.services import conversation_streaming as cs

    out = list(cs._stream_via_cli([{"role": "user", "content": "hi"}], model="claude-x", cwd="/ws"))
    assert any("blocked by policy" in o for o in out), out


def test_conversation_opencode_refused(deny_and_degrade):
    from app.services import conversation_streaming as cs

    out = list(
        cs._stream_via_opencode_cli(
            [{"role": "user", "content": "hi"}], model="prov/model", cwd="/ws"
        )
    )
    assert any("blocked by policy" in o for o in out), out


# --------------------------------------------------------------------------- #
# crit 8 — base_generation_service.generate_streaming (generator)
# --------------------------------------------------------------------------- #
def test_base_generation_refused(deny_and_degrade):
    from app.services.base_generation_service import BaseGenerationService

    class _DummyGen(BaseGenerationService):
        @classmethod
        def _gather_context(cls):
            return {}

        @classmethod
        def _build_prompt(cls, description, context):
            return "p"

        @classmethod
        def _extract_progress(cls, text, reported):
            return []

        @classmethod
        def _validate(cls, config):
            return ({}, [])

    events = list(_DummyGen.generate_streaming("make something"))
    assert any("Launch blocked by policy" in e for e in events), events


# --------------------------------------------------------------------------- #
# crit 9 — replay_service._run_replay_subprocess (records FAILED, no spawn)
# --------------------------------------------------------------------------- #
def test_replay_refused(deny_and_degrade):
    from app.services import replay_service
    from app.services.replay_service import ReplayService

    recorded = {}
    replay_service.ExecutionLogService.finish_execution = staticmethod(
        lambda **kw: recorded.update(kw)
    )

    ReplayService._run_replay_subprocess(
        execution_id="ex-1", cmd_str="claude -p x", trigger_id="t-1", backend_type="claude"
    )
    assert recorded.get("status") == "failed"
    assert "policy" in (recorded.get("error_message") or "").lower()


# --------------------------------------------------------------------------- #
# crit 7 — project_session_manager.create_session (the chokepoint) — refuses
# before any pty.fork / subprocess.Popen.
# --------------------------------------------------------------------------- #
def test_create_session_refused(deny_and_degrade):
    import os

    from app.services.project_session_manager import ProjectSessionManager

    def _no_fork():  # pragma: no cover - asserted not to run
        raise AssertionError("os.fork must not run when the launch is refused")

    deny_and_degrade.setattr(os, "fork", _no_fork)

    with pytest.raises(PolicyDenied):
        ProjectSessionManager.create_session(
            project_id="proj-x",
            cmd=["claude", "-p", "x"],
            cwd="/ws",
            use_pty=False,
        )
