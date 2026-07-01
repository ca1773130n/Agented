"""L1 tests for the optional cloud-sandbox runners (24-04).

Runner selection + absent-credential graceful skip + no-ImportError-when-absent,
plus that both highest-risk autonomous consumers consult select_runner. No live
E2B/Modal round-trip (that needs credentials — L3, out of CI scope).
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


def test_process_project_autonomy_consults_select_runner(monkeypatch):
    from app.services import harness_autonomy

    spy = {"risk": None}

    def _fake_select(*, risk, config=None):
        spy["risk"] = risk
        return LocalRunner(config)

    monkeypatch.setattr(csr, "select_runner", _fake_select)

    class _Policy:
        enabled = True
        cooldown_seconds = 0

    monkeypatch.setattr(harness_autonomy.autonomy_cfg, "get_policy", lambda pid: _Policy())
    monkeypatch.setattr(harness_autonomy.evo_repo, "list_for_project", lambda pid, limit=50: [])

    out = harness_autonomy.process_project_autonomy("proj-x")
    assert out == []
    assert spy["risk"] == "high"


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
