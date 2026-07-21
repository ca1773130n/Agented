"""GRD 0.5.0 interactive-checkpoint integration: resume --answers plumbing +
GRD_AUTOPILOT for unattended runs."""

import json
import re

import pytest

from app.services import execution_type_handler as eth
from app.services.execution_type_handler import GrdResearchSessionHandler


def _mock_session(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        eth.ProjectSessionManager,
        "create_session",
        staticmethod(lambda **k: (captured.update(k), "sess-1")[1]),
    )
    monkeypatch.setattr(
        eth.ProjectSessionManager, "get_session_info", staticmethod(lambda sid: {"pid": 1})
    )
    return captured


def test_resume_with_answers_writes_qid_keyed_file_and_flag(monkeypatch, tmp_path):
    captured = _mock_session(monkeypatch)
    res = GrdResearchSessionHandler().start(
        {
            "project_id": "p1",
            "thread_id": "th-1",
            "cwd": str(tmp_path),
            "execution_mode": "attended",  # isolate the answers path from autopilot
            "answers": [
                {"question_id": "q1", "label": "Option A", "text": "because reasons"},
                {"question_id": "q2", "label": "Option B"},
            ],
        }
    )
    assert res["session_id"] == "sess-1"
    prompt = captured["cmd"][-1]
    assert "/grd:research resume" in prompt and "--answers" in prompt

    m = re.search(r'--answers ("(?:[^"\\]|\\.)*"|\S+)', prompt)
    path = json.loads(m.group(1)) if m.group(1).startswith('"') else m.group(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # object keyed by question id, freeform text preserved, optional text omitted
    assert data == {
        "q1": {"label": "Option A", "text": "because reasons"},
        "q2": {"label": "Option B"},
    }


def test_resume_without_answers_has_no_flag(monkeypatch, tmp_path):
    captured = _mock_session(monkeypatch)
    GrdResearchSessionHandler().start(
        {"project_id": "p1", "thread_id": "th-1", "cwd": str(tmp_path), "execution_mode": "attended"}
    )
    assert "--answers" not in captured["cmd"][-1]


def test_autonomous_run_sets_autopilot_attended_does_not(monkeypatch, tmp_path):
    captured = _mock_session(monkeypatch)
    GrdResearchSessionHandler().start(
        {"project_id": "p", "question": "q", "cwd": str(tmp_path), "execution_mode": "autonomous"}
    )
    assert captured.get("env") == {"GRD_AUTOPILOT": "1"}

    captured.clear()
    GrdResearchSessionHandler().start(
        {"project_id": "p", "question": "q", "cwd": str(tmp_path), "execution_mode": "attended"}
    )
    assert captured.get("env") is None


def _interactive(tmp_path):
    p = tmp_path / ".planning" / "config.json"
    return json.loads(p.read_text())["research_gates"]["interactive"] if p.exists() else None


def test_steering_autopilot_disables_interactive(monkeypatch, tmp_path):
    captured = _mock_session(monkeypatch)
    GrdResearchSessionHandler().start(
        {"project_id": "p", "question": "q", "cwd": str(tmp_path), "research_steering": "autopilot"}
    )
    assert captured.get("env") == {"GRD_AUTOPILOT": "1"}
    # autopilot pins enabled=false so it can't inherit a prior panel run
    assert _interactive(tmp_path) == {"enabled": False}


def test_autopilot_clears_stale_panel_config(monkeypatch, tmp_path):
    # codex Medium: a prior `panel` run leaves enabled+fallback=panel behind;
    # a later autopilot run must override it, not silently engage the panel.
    _mock_session(monkeypatch)
    h = GrdResearchSessionHandler()
    h.start({"project_id": "p", "question": "q", "cwd": str(tmp_path), "research_steering": "panel"})
    assert _interactive(tmp_path) == {"enabled": True, "fallback": "panel"}
    h.start({"project_id": "p", "question": "q", "cwd": str(tmp_path), "research_steering": "autopilot"})
    # fallback persists as a key but enabled=false disables the panel entirely
    assert _interactive(tmp_path)["enabled"] is False


def test_ensure_interactive_config_fails_closed_on_malformed(tmp_path):
    cfg = tmp_path / ".planning" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{ not valid json ")
    with pytest.raises(ValueError):
        GrdResearchSessionHandler._ensure_interactive_config(str(tmp_path), {"enabled": True})
    # the corrupt file is left intact, NOT overwritten with just our block
    assert cfg.read_text() == "{ not valid json "


def test_steering_panel_enables_interactive_with_panel_fallback(monkeypatch, tmp_path):
    captured = _mock_session(monkeypatch)
    GrdResearchSessionHandler().start(
        {"project_id": "p", "question": "q", "cwd": str(tmp_path), "research_steering": "panel"}
    )
    # panel is still headless (never hangs) but resolves each gate via the AI panel
    assert captured.get("env") == {"GRD_AUTOPILOT": "1"}
    assert _interactive(tmp_path) == {"enabled": True, "fallback": "panel"}


def test_steering_attended_enables_pause_and_no_autopilot(monkeypatch, tmp_path):
    captured = _mock_session(monkeypatch)
    GrdResearchSessionHandler().start(
        {"project_id": "p", "question": "q", "cwd": str(tmp_path), "research_steering": "attended"}
    )
    assert captured.get("env") is None  # a human can steer → no autopilot
    assert _interactive(tmp_path) == {"enabled": True}


def test_ensure_interactive_config_preserves_existing_keys(tmp_path):
    cfg = tmp_path / ".planning" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"foo": 1, "research_gates": {"execute": True, "interactive": {"seed": True}}}))
    GrdResearchSessionHandler._ensure_interactive_config(str(tmp_path), {"enabled": True, "fallback": "panel"})
    data = json.loads(cfg.read_text())
    assert data["foo"] == 1  # unrelated top-level key preserved
    assert data["research_gates"]["execute"] is True  # sibling gate preserved
    # existing interactive knob preserved, ours merged on top
    assert data["research_gates"]["interactive"] == {"seed": True, "enabled": True, "fallback": "panel"}
