"""L1 tests for the optional cloud-sandbox runners (24-04).

Runner selection + absent-credential graceful skip + no-ImportError-when-absent.
The competitor-strategy auto-implement consumer consults select_runner; the
harness-autonomy patch-apply consumer does NOT (24-fix MAJOR 2 — patch-apply is a
local git op, not a spawn). A cloud runner handed goal-loop work falls back to the
local goal-loop rather than running a degraded cmd-only stub (24-fix BLOCKER 3). No
live E2B/Modal round-trip (that needs credentials — L3, out of CI scope).
"""

import importlib
import shlex
import sys
import types
from pathlib import Path

from app.services import cloud_sandbox_runner as csr
from app.services.cloud_sandbox_runner import (
    E2BRunner,
    LocalRunner,
    ModalRunner,
    select_runner,
)

_SERVICES = Path(__file__).resolve().parent.parent / "app" / "services"


def _clear_cloud_creds(monkeypatch):
    for k in ("E2B_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"):
        monkeypatch.delenv(k, raising=False)


def test_select_runner_local_without_creds(monkeypatch):
    _clear_cloud_creds(monkeypatch)
    logged = []
    monkeypatch.setattr(csr.logger, "info", lambda *a, **k: logged.append(a))
    runner = select_runner(risk="high", config={"project_id": "p1"})
    assert isinstance(runner, LocalRunner)
    assert logged, "expected a graceful-skip info log"


def test_select_runner_e2b_with_key(monkeypatch):
    _clear_cloud_creds(monkeypatch)
    monkeypatch.setenv("E2B_API_KEY", "e2b-xxx")
    runner = select_runner(risk="high", config={})
    assert isinstance(runner, E2BRunner)


def test_select_runner_modal_with_tokens(monkeypatch):
    _clear_cloud_creds(monkeypatch)
    monkeypatch.setenv("MODAL_TOKEN_ID", "id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "secret")
    runner = select_runner(risk="high", config={})
    assert isinstance(runner, ModalRunner)


def test_e2b_preferred_over_modal(monkeypatch):
    _clear_cloud_creds(monkeypatch)
    monkeypatch.setenv("E2B_API_KEY", "e2b-xxx")
    monkeypatch.setenv("MODAL_TOKEN_ID", "id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "secret")
    assert isinstance(select_runner(risk="high", config={}), E2BRunner)


def test_low_risk_always_local(monkeypatch):
    _clear_cloud_creds(monkeypatch)
    monkeypatch.setenv("E2B_API_KEY", "e2b-xxx")
    runner = select_runner(risk="normal", config={})
    assert isinstance(runner, LocalRunner)


def test_absent_creds_no_importerror(monkeypatch):
    """Module import + select_runner must not require e2b/modal to be installed."""
    _clear_cloud_creds(monkeypatch)
    # Simulate the SDKs being absent/broken; lazy imports mean select_runner never
    # touches them, so this must NOT raise.
    monkeypatch.setitem(sys.modules, "e2b", None)
    monkeypatch.setitem(sys.modules, "modal", None)
    reloaded = importlib.reload(csr)
    runner = reloaded.select_runner(risk="high", config={})
    assert reloaded.LocalRunner is type(runner) or isinstance(runner, reloaded.LocalRunner)
    # Restore a clean module for the rest of the suite.
    importlib.reload(csr)


def test_local_runner_wrap_delegates(monkeypatch):
    from app.services import sandbox_wrap

    monkeypatch.setattr(sandbox_wrap, "sandbox_available", lambda: False)
    runner = LocalRunner()
    out, sandboxed = runner.wrap(["echo", "x"], "/ws")
    assert out == ["echo", "x"]
    assert sandboxed is False


def test_process_project_autonomy_does_not_select_runner(monkeypatch):
    """MAJOR 2 (24-fix): autonomy's apply is a LOCAL git patch-apply
    (``apply_dry_run_round``), not a spawnable command, so it must NOT select a cloud
    runner. The prior select-then-ignore dead routing is removed — ``select_runner``
    is never consulted here."""
    from app.services import harness_autonomy

    calls = {"n": 0}

    def _boom_select(*a, **k):
        calls["n"] += 1
        raise AssertionError("process_project_autonomy must not select a runner")

    monkeypatch.setattr(csr, "select_runner", _boom_select)

    class _Policy:
        enabled = True
        cooldown_seconds = 0

    monkeypatch.setattr(harness_autonomy.autonomy_cfg, "get_policy", lambda pid: _Policy())
    monkeypatch.setattr(harness_autonomy.evo_repo, "list_for_project", lambda pid, limit=50: [])

    out = harness_autonomy.process_project_autonomy("proj-x")
    assert out == []
    assert calls["n"] == 0


def test_start_autoimplement_wires_select_runner():
    """Source-level assertion: the auto-implement seam consults select_runner
    (the full triple-gated path is exercised elsewhere; here we prove the wiring)."""
    src = (_SERVICES / "competitor_strategy_service.py").read_text()
    assert "select_runner" in src
    assert 'risk="high"' in src


# --------------------------------------------------------------------------- #
# MAJOR 10 (24-fix): no shell injection via " ".join(cmd).
# --------------------------------------------------------------------------- #
def test_e2b_run_quotes_shell_metacharacters(monkeypatch):
    captured = {}

    class _FakeCommands:
        def run(self, cmd_str):
            captured["cmd_str"] = cmd_str
            return "ok"

    class _FakeSbx:
        commands = _FakeCommands()

        def kill(self):
            pass

    class _FakeSandbox:
        @staticmethod
        def create(timeout=300):
            return _FakeSbx()

    fake_e2b = types.ModuleType("e2b")
    fake_e2b.Sandbox = _FakeSandbox
    monkeypatch.setitem(sys.modules, "e2b", fake_e2b)

    argv = ["echo", "a; rm -rf /"]
    E2BRunner().run(argv)
    # The metacharacter arg is passed as a single QUOTED token, not interpreted.
    assert captured["cmd_str"] == shlex.join(argv)
    assert captured["cmd_str"] != " ".join(argv)
    assert "'a; rm -rf /'" in captured["cmd_str"]


def test_modal_run_uses_argv_without_shell(monkeypatch):
    calls = {}

    class _FakeSb:
        def exec(self, *args, timeout=None):
            calls["args"] = args
            calls["timeout"] = timeout
            return "proc"

        def terminate(self):
            pass

    class _FakeApp:
        @staticmethod
        def lookup(name, create_if_missing=False):
            return object()

    class _FakeSandbox:
        @staticmethod
        def create(app=None):
            return _FakeSb()

    fake_modal = types.ModuleType("modal")
    fake_modal.App = _FakeApp
    fake_modal.Sandbox = _FakeSandbox
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    argv = ["echo", "a; rm -rf /"]
    ModalRunner().run(argv)
    # argv passed verbatim, no "bash -lc <joined>" shell wrapper.
    assert calls["args"] == tuple(argv)
    assert "bash" not in calls["args"]
    assert "-lc" not in calls["args"]


# --------------------------------------------------------------------------- #
# MAJOR 11 (24-fix): the SELECTED runner actually executes (dead routing fixed).
# --------------------------------------------------------------------------- #
def test_local_runner_execute_delegates_to_goal_loop(monkeypatch):
    started = {}

    class _Handler:
        def start(self, cfg):
            started["cfg"] = cfg
            return {"session_id": "psess-1"}

    monkeypatch.setattr("app.services.execution_type_handler.get_handler", lambda kind: _Handler())
    out = LocalRunner().execute({"cmd": ["claude"], "marker": 42})
    assert out == {"session_id": "psess-1"}
    assert started["cfg"]["marker"] == 42


def test_selected_cloud_runner_executes(monkeypatch):
    """High-risk + credentialed selects E2BRunner AND its execute() runs the cmd via
    the (mocked) cloud SDK — proving the selected runner is the one that executes."""
    _clear_cloud_creds(monkeypatch)
    monkeypatch.setenv("E2B_API_KEY", "e2b-xxx")
    # Reference through ``csr`` — an earlier test reloads the module, which would
    # leave the top-level ``select_runner``/``E2BRunner`` imports stale.
    runner = csr.select_runner(risk="high", config={})
    assert isinstance(runner, csr.E2BRunner)

    ran = {}

    class _FakeCommands:
        def run(self, cmd_str):
            ran["cmd_str"] = cmd_str
            return "cloud-ok"

    class _FakeSbx:
        commands = _FakeCommands()

        def kill(self):
            pass

    class _FakeSandbox:
        @staticmethod
        def create(timeout=300):
            return _FakeSbx()

    fake_e2b = types.ModuleType("e2b")
    fake_e2b.Sandbox = _FakeSandbox
    monkeypatch.setitem(sys.modules, "e2b", fake_e2b)

    result = runner.execute({"cmd": ["claude", "--goal", "x"]})
    assert result["runner"] == "e2b"
    assert result["result"] == "cloud-ok"
    assert ran["cmd_str"] == shlex.join(["claude", "--goal", "x"])


def test_competitor_strategy_routes_through_runner_execute():
    """Source-level: execution goes through runner.execute, NOT the local handler
    directly — the dead-routing bug (selected runner ignored) is closed."""
    src = (_SERVICES / "competitor_strategy_service.py").read_text()
    assert "runner.execute(session_config)" in src
    assert "handler.start(session_config)" not in src


# --------------------------------------------------------------------------- #
# BLOCKER 3 (24-fix): a cmd-only cloud runner must NOT silently run goal-loop work.
# --------------------------------------------------------------------------- #
def test_requires_goal_loop_detection():
    from app.services.cloud_sandbox_runner import _requires_goal_loop

    assert _requires_goal_loop({"goal_loop_config": {"goal": "x"}}) is True
    assert _requires_goal_loop({"execution_type": "goal_loop"}) is True
    assert _requires_goal_loop({"requires_goal_loop": True}) is True
    assert _requires_goal_loop({"cmd": ["claude"]}) is False
    assert _requires_goal_loop(None) is False


def test_cloud_runner_goal_loop_falls_back_to_local(monkeypatch):
    """BLOCKER 3 (24-fix): a cloud runner (E2B/Modal) handed goal-loop work must NOT
    run the cmd-only cloud stub (which returns a SYNTHETIC id while the caller
    believes a governed PSM goal-loop ran). It falls back to the LOCAL goal-loop.

    Asserts: no synthetic ``e2b-``/``modal-`` id is produced for goal-loop work, the
    real local goal-loop handler runs, and the cloud ``run()`` stub is never called."""
    from app.services import execution_type_handler

    started = {}

    class _Handler:
        def start(self, cfg):
            started["cfg"] = cfg
            return {"session_id": "psess-real"}

    monkeypatch.setattr(execution_type_handler, "get_handler", lambda kind: _Handler())

    # If the degraded cmd-only path were taken, .run() would fire — make it explode so
    # any degraded stub path fails loudly rather than silently.
    def _boom_run(self, cmd, *, timeout=300):
        raise AssertionError("cloud cmd-only stub must not run for goal-loop work")

    monkeypatch.setattr(csr.E2BRunner, "run", _boom_run)
    monkeypatch.setattr(csr.ModalRunner, "run", _boom_run)

    session_config = {
        "cmd": ["claude", "--dangerously-skip-permissions"],
        "execution_type": "goal_loop",
        "goal_loop_config": {"goal": "do it", "max_iterations": 3},
    }

    for runner_cls in (csr.E2BRunner, csr.ModalRunner):
        out = runner_cls({"project_id": "p"}).execute(session_config)
        assert out == {"session_id": "psess-real"}
        assert not str(out.get("session_id", "")).startswith(("e2b-", "modal-"))
    assert started["cfg"]["goal_loop_config"]["goal"] == "do it"
