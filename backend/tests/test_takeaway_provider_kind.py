"""Provider-kind threading through LLM takeaway extraction."""

from __future__ import annotations

from unittest.mock import patch

from app.services import harness_takeaway_extractor as tx
from app.services.harness_failure_annotator import SessionPayload


def _payload(text: str) -> SessionPayload:
    return SessionPayload(
        text=text, backend_type="claude", project_id="proj-1", outcome="completed"
    )


def test_extract_llm_uses_provider_cmd(monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    captured = {}

    def _fake_run(prompt, *, cmd_template, timeout):
        captured["cmd_template"] = cmd_template
        return "[]"

    big_text = "x" * 5000  # exceed _llm_min_text_bytes
    with patch.object(tx, "_run_llm_for_extraction", _fake_run):
        tx._extract_llm("super_agent", "s-1", "proj-1", _payload(big_text), provider_kind="gemini")

    assert captured["cmd_template"][0] == "gemini"


def test_extract_llm_disabled_returns_empty(monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "0")
    with patch.object(tx, "_run_llm_for_extraction") as m:
        out = tx._extract_llm(
            "super_agent", "s-1", "proj-1", _payload("x" * 5000), provider_kind="anthropic"
        )
    assert out == []
    m.assert_not_called()
