"""L2 gate test (24-03, crit 4): the Phase-23 enforce_sandbox verdict now REFUSES
an unsandboxable launch.

Exercises the REAL merged Phase-23 API — ``PolicyService.enforce_launch`` +
``PolicyDenied`` + the ``enforce_sandbox`` builtin — through the Phase-24 launch
seam ``ExecutionService._apply_sandbox_and_enforce``. With a seeded ``enforce_sandbox``
DENY policy: a degraded (``sandboxed=False``) launch is refused (PolicyDenied,
Popen never reached); a real-sandbox (``sandboxed=True``) launch proceeds.
"""

import subprocess

import pytest

from app.services import sandbox_wrap
from app.services.execution_service import ExecutionService
from app.services.policy_service import PolicyDenied, PolicyService


def _seed_enforce_sandbox_deny():
    # Server-scope policy that DENIES any non-sandboxed process launch.
    PolicyService.create_policy(
        scope="server",
        scope_id=None,
        kind="enforce_sandbox",
        effect="deny",
        params={"require_sandbox": True},
        priority=100,
    )


def test_enforce_sandbox_deny_refuses_unsandboxed_launch(isolated_db, monkeypatch):
    _seed_enforce_sandbox_deny()
    # Sandbox degraded / disabled ⇒ wrap yields the bare cmd + sandboxed=False.
    monkeypatch.setattr(
        sandbox_wrap, "wrap_harness_command", lambda cmd, ws, **k: (list(cmd), False)
    )
    # Popen sentinel: it must NEVER be called when the gate refuses the launch.
    popen_called = {"hit": False}

    def _sentinel(*a, **k):  # pragma: no cover - asserted not to run
        popen_called["hit"] = True
        raise AssertionError("Popen must not run when the launch is policy-blocked")

    monkeypatch.setattr(subprocess, "Popen", _sentinel)

    with pytest.raises(PolicyDenied):
        ExecutionService._apply_sandbox_and_enforce(
            ["claude", "-p", "hi"],
            "/ws",
            session_id="sess-deny",
            team_id=None,
            backend="claude",
        )
    assert popen_called["hit"] is False


def test_sandboxed_true_proceeds(isolated_db, monkeypatch):
    _seed_enforce_sandbox_deny()
    # Real sandbox engaged ⇒ sandboxed=True ⇒ enforce_sandbox ALLOWS.
    monkeypatch.setattr(
        sandbox_wrap,
        "wrap_harness_command",
        lambda cmd, ws, **k: (["bwrap", "--", *cmd], True),
    )
    wrapped, sandboxed = ExecutionService._apply_sandbox_and_enforce(
        ["claude", "-p", "hi"],
        "/ws",
        session_id="sess-allow",
        team_id=None,
        backend="claude",
    )
    assert sandboxed is True
    assert wrapped[0] == "bwrap"
    assert wrapped[-3:] == ["claude", "-p", "hi"]


def test_no_policy_allows_unsandboxed_launch(isolated_db, monkeypatch):
    # No enforce_sandbox policy ⇒ a non-sandboxed launch is permitted (default allow).
    monkeypatch.setattr(
        sandbox_wrap, "wrap_harness_command", lambda cmd, ws, **k: (list(cmd), False)
    )
    wrapped, sandboxed = ExecutionService._apply_sandbox_and_enforce(
        ["claude", "-p", "hi"],
        "/ws",
        session_id="sess-open",
        team_id=None,
        backend="claude",
    )
    assert sandboxed is False
    assert wrapped == ["claude", "-p", "hi"]
