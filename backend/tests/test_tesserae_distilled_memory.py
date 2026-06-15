"""Tesserae 0.9.0 distilled-memory wiring (milestone sub-project #2).

CLI mocked at the subprocess boundary; DB exercised against ``isolated_db``.
Covers the per-project distill toggle, compile's modern ``tesserae compile
--distill`` argv, ``context_tesserae`` multi-pool retrieval, and the
kg-signal dispatch (context when distill on, ask otherwise).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services import harness_kg_signals as kg
from app.services import tesserae_integration as ti


def _seed(project_id: str, root: Path, *, distill: int = 0) -> None:
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, local_path, "
            "tesserae_project_root, tesserae_distill_enabled) VALUES (?,?,?,?,?)",
            (project_id, "T", str(root), str(root), distill),
        )
        conn.commit()


class _Done:
    def __init__(self, rc: int = 0, out: str = "ok", err: str = "") -> None:
        self.returncode = rc
        self.stdout = out
        self.stderr = err


# ---- toggle round-trip --------------------------------------------------

def test_distill_flag_roundtrips(isolated_db, tmp_path):
    _seed("proj-d1", tmp_path, distill=0)
    assert ti.get_distill_enabled("proj-d1") is False
    ti.set_distill_enabled("proj-d1", True)
    assert ti.get_distill_enabled("proj-d1") is True
    ti.set_distill_enabled("proj-d1", False)
    assert ti.get_distill_enabled("proj-d1") is False


def test_get_distill_false_for_unknown_project(isolated_db):
    assert ti.get_distill_enabled("nope") is False


# ---- compile uses modern `tesserae compile` + distill flag --------------

def test_compile_uses_modern_command_with_distill_when_on(isolated_db, tmp_path):
    _seed("proj-c1", tmp_path, distill=1)
    captured: dict = {}
    with patch.object(
        ti.subprocess, "run",
        side_effect=lambda cmd, **kw: captured.update(cmd=cmd) or _Done(),
    ):
        res = ti.compile_workspace("proj-c1")
    assert res.ok
    cmd = captured["cmd"]
    assert cmd[:2] == [ti._TESSERAE_CMD, "compile"]  # modern, NOT `project compile`
    assert "project" not in cmd[:2]
    assert "--distill" in cmd
    assert "--no-distill" not in cmd
    assert "--project" in cmd and str(tmp_path) in cmd


def test_compile_passes_no_distill_when_off(isolated_db, tmp_path):
    _seed("proj-c2", tmp_path, distill=0)
    captured: dict = {}
    with patch.object(
        ti.subprocess, "run",
        side_effect=lambda cmd, **kw: captured.update(cmd=cmd) or _Done(),
    ):
        ti.compile_workspace("proj-c2")
    cmd = captured["cmd"]
    assert "--no-distill" in cmd
    assert "--distill" not in cmd


# ---- context_tesserae (multi-pool) --------------------------------------

def test_context_tesserae_argv_and_text(isolated_db, tmp_path):
    _seed("proj-ctx", tmp_path)
    captured: dict = {}
    with patch.object(
        ti.subprocess, "run",
        side_effect=lambda cmd, **kw: captured.update(cmd=cmd) or _Done(out="DOC"),
    ):
        out = ti.context_tesserae("proj-ctx", "what is X?", multi_pool=True, budget=4000)
    assert out == "DOC"
    cmd = captured["cmd"]
    assert cmd[:2] == [ti._TESSERAE_CMD, "context"]
    assert "what is X?" in cmd
    assert "--multi-pool" in cmd
    assert "--project" in cmd and str(tmp_path) in cmd
    assert "--budget" in cmd and "4000" in cmd


def test_context_tesserae_omits_multipool_when_false(isolated_db, tmp_path):
    _seed("proj-ctx3", tmp_path)
    captured: dict = {}
    with patch.object(
        ti.subprocess, "run",
        side_effect=lambda cmd, **kw: captured.update(cmd=cmd) or _Done(out="x"),
    ):
        ti.context_tesserae("proj-ctx3", "q", multi_pool=False)
    assert "--multi-pool" not in captured["cmd"]


def test_context_tesserae_none_on_failure(isolated_db, tmp_path):
    _seed("proj-ctx2", tmp_path)
    with patch.object(
        ti.subprocess, "run",
        side_effect=lambda cmd, **kw: _Done(rc=2, out="", err="boom"),
    ):
        assert ti.context_tesserae("proj-ctx2", "q") is None


# ---- kg-signal dispatch by toggle ---------------------------------------

def _patch_kg(monkeypatch, tmp_path, *, distill: bool):
    monkeypatch.setattr(kg, "get_tesserae_root", lambda pid: tmp_path)
    monkeypatch.setattr(kg, "get_distill_enabled", lambda pid: distill)
    calls = {"ask": 0, "ctx": 0}
    monkeypatch.setattr(
        kg, "ask_tesserae",
        lambda *a, **k: calls.__setitem__("ask", calls["ask"] + 1) or None,
    )
    monkeypatch.setattr(
        kg, "context_tesserae",
        lambda *a, **k: calls.__setitem__("ctx", calls["ctx"] + 1) or None,
    )
    return calls


def test_kg_signals_uses_context_when_distill_on(isolated_db, tmp_path, monkeypatch):
    calls = _patch_kg(monkeypatch, tmp_path, distill=True)
    kg.gather_kg_signals("proj-kg")
    assert calls["ctx"] > 0
    assert calls["ask"] == 0


def test_kg_signals_uses_ask_when_distill_off(isolated_db, tmp_path, monkeypatch):
    calls = _patch_kg(monkeypatch, tmp_path, distill=False)
    kg.gather_kg_signals("proj-kg2")
    assert calls["ask"] > 0
    assert calls["ctx"] == 0


# ---- route + per-project state ------------------------------------------

def test_per_project_state_reflects_distill_toggle(isolated_db):
    # The route handler is thin glue over set_distill_enabled +
    # _tesserae_per_project_state (the handler is decorated, so it's exercised
    # via the app, not called directly). This covers the new column flowing
    # through to the operator-facing state row.
    from app.db.projects import create_project
    from app_litestar.routes.memory_system import _tesserae_per_project_state

    pid = create_project("DistillState")

    def row():
        return next(p for p in _tesserae_per_project_state() if p["project_id"] == pid)

    assert row()["distill_enabled"] is False
    ti.set_distill_enabled(pid, True)
    assert row()["distill_enabled"] is True
    ti.set_distill_enabled(pid, False)
    assert row()["distill_enabled"] is False
