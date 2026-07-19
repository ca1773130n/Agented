"""GRD 0.5.0 interactive-checkpoint integration: resume --answers plumbing +
GRD_AUTOPILOT for unattended runs."""

import json
import re

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
