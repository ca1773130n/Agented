"""Phase 23 — workflow command/script nodes route through the shared launch gate.

BUG (closed here): ``workflow_node_executor._run_in_process_group`` spawned
command/script node subprocesses via ``subprocess.Popen`` WITHOUT consulting
``PolicyService.enforce_launch`` — the one shared gate every other autonomous
spawner (run_trigger, create_session) clears. Workflow execution is autonomous,
so an ungated node was a governance bypass: a server-scope DENY that blocks
every launch could be sidestepped by routing the work through a workflow.

These tests prove a DENY policy now blocks the node BEFORE any subprocess is
spawned (fail closed), and that the default-ALLOW path still runs (no
regression on the happy path).
"""

import subprocess

import pytest

from app.models.workflow import WorkflowMessage
from app.services import workflow_node_executor as wne
from app.services.policy_service import PolicyDenied
from app.services.workflow_node_executor import NodeExecutor


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


def _msg():
    return WorkflowMessage(metadata={"_execution_id": "wf-exec-1"})


def test_denied_policy_blocks_command_node_subprocess(isolated_db, monkeypatch):
    """A server-scope DENY raises PolicyDenied from _execute_command_node BEFORE
    subprocess.Popen is ever called."""
    _seed("server", None, "deny", kind="manual")

    spawned = {"n": 0}

    def _boom(*a, **k):
        spawned["n"] += 1
        raise AssertionError("no subprocess may spawn when policy denies the launch")

    monkeypatch.setattr(wne.subprocess, "Popen", _boom)

    with pytest.raises(PolicyDenied):
        NodeExecutor._execute_command_node("n1", {"command": "echo hi"}, _msg())
    assert spawned["n"] == 0


def test_denied_policy_blocks_script_node_subprocess(isolated_db, monkeypatch):
    """Same bypass closed for the script node — its launch funnels through the
    same _run_in_process_group chokepoint."""
    _seed("server", None, "deny", kind="manual")

    spawned = {"n": 0}

    def _boom(*a, **k):
        spawned["n"] += 1
        raise AssertionError("no subprocess may spawn when policy denies the launch")

    monkeypatch.setattr(wne.subprocess, "Popen", _boom)

    with pytest.raises(PolicyDenied):
        NodeExecutor._execute_script_node(
            "n2", {"script": "print('hi')", "interpreter": "python3"}, _msg()
        )
    assert spawned["n"] == 0


def test_session_scope_deny_blocks_workflow_execution_id(isolated_db, monkeypatch):
    """The node's SESSION policy key is the workflow execution id (session-not-bot
    rule): a session-scope DENY keyed to that id blocks the node."""
    _seed("session", "wf-exec-1", "deny", kind="manual")

    monkeypatch.setattr(
        wne.subprocess,
        "Popen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )

    with pytest.raises(PolicyDenied):
        NodeExecutor._execute_command_node("n3", {"command": "echo hi"}, _msg())


def test_default_allow_lets_command_node_run(isolated_db):
    """No policy authored → default ALLOW → the gate is transparent and the
    command node runs to completion (happy-path regression guard)."""
    out = NodeExecutor._execute_command_node("n4", {"command": "echo policy-ok"}, _msg())
    assert out.exit_code == 0
    assert "policy-ok" in (out.stdout or "")


def test_gate_runs_before_popen_for_allow(isolated_db, monkeypatch):
    """Even on ALLOW, enforce_launch is evaluated BEFORE Popen — assert the gate
    fires (spy) and then Popen is reached exactly once."""
    seen = {"gate": 0}

    from app.services.policy_service import PolicyService

    orig = PolicyService.enforce_launch.__func__

    def _spy(cls, **kw):
        seen["gate"] += 1
        return orig(cls, **kw)

    monkeypatch.setattr(PolicyService, "enforce_launch", classmethod(_spy))

    captured = {"popen": 0}
    real_popen = subprocess.Popen

    def _count_popen(*a, **k):
        captured["popen"] += 1
        return real_popen(*a, **k)

    monkeypatch.setattr(wne.subprocess, "Popen", _count_popen)

    NodeExecutor._execute_command_node("n5", {"command": "echo gate-order"}, _msg())
    assert seen["gate"] == 1
    assert captured["popen"] == 1
