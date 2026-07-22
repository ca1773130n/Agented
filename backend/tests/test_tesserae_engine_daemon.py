"""Tesserae 0.23/0.24 sleep-cycle daemon supervisor — the enable gate, status
shape, and env/argv it spawns. No real `tesserae` process is started (Popen is
stubbed); this locks the Agented-side supervision contract."""

import pytest

from app.services import tesserae_engine_daemon as ted


@pytest.fixture(autouse=True)
def _reset_handle():
    """Never let a stubbed process handle leak between tests."""
    ted.TesseraeEngineDaemon._process = None
    yield
    ted.TesseraeEngineDaemon._process = None


def test_enabled_default_on(monkeypatch):
    monkeypatch.delenv("AGENTED_TESSERAE_CONSOLIDATE", raising=False)
    assert ted._enabled() is True


@pytest.mark.parametrize("val", ["1", "true", "YES", "on"])
def test_enabled_truthy(monkeypatch, val):
    monkeypatch.setenv("AGENTED_TESSERAE_CONSOLIDATE", val)
    assert ted._enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
def test_disabled_gate_blocks_start(monkeypatch, val):
    monkeypatch.setenv("AGENTED_TESSERAE_CONSOLIDATE", val)
    # start() must be a no-op even if Popen would otherwise succeed.
    monkeypatch.setattr(
        ted.subprocess, "Popen", lambda *a, **k: pytest.fail("must not spawn when disabled")
    )
    assert ted.TesseraeEngineDaemon.start() is False
    st = ted.TesseraeEngineDaemon.status()
    assert st["enabled"] is False and st["running"] is False


def test_status_shape(monkeypatch):
    monkeypatch.delenv("AGENTED_TESSERAE_CONSOLIDATE", raising=False)
    st = ted.TesseraeEngineDaemon.status()
    assert set(st) == {"enabled", "running", "idle_seconds", "consolidate_every"}
    assert st["idle_seconds"] == 300 and st["consolidate_every"] == 21600
    assert st["running"] is False  # nothing spawned


def test_start_spawns_consolidate_with_distill_env(monkeypatch):
    monkeypatch.setenv("AGENTED_TESSERAE_CONSOLIDATE", "1")
    # AGENTED_SERVER_NO_LLM_KEYS off → env is os.environ copy + the distill flag.
    monkeypatch.delenv("AGENTED_SERVER_NO_LLM_KEYS", raising=False)
    monkeypatch.setattr(ted.TesseraeEngineDaemon, "kill_orphans", classmethod(lambda cls: None))
    captured: dict = {}

    class _Proc:
        pid = 4242

        def poll(self):
            return None  # alive

    def _popen(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env")
        return _Proc()

    monkeypatch.setattr(ted.subprocess, "Popen", _popen)
    assert ted.TesseraeEngineDaemon.start() is True
    assert captured["cmd"][1:4] == ["engine", "--all", "--consolidate"]
    assert captured["env"]["TESSERAE_AGENT_DISTILL"] == "1"
    assert ted.TesseraeEngineDaemon.status()["running"] is True
