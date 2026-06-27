"""Federated Tesserae retrieval + the Sketch ideation streaming service.

The Sketch page is a grounded ideation chat: each turn pulls FEDERATED context
across all registered Tesserae projects and streams a general-LLM reply, with no
routing/execution until the operator clicks Route. These tests mock the Tesserae
subprocess and the LLM stream — no network, no real Tesserae.
"""

from __future__ import annotations

from app.services import sketch_ideation_service as sis
from app.services import tesserae_integration as ti


class _R:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_federated_ask_parses_envelope_and_scopes_all_projects(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "list" in cmd:
            return _R(stdout='{"active":"a","projects":[{"name":"a"},{"name":"b"}]}')
        # progress preamble before the JSON must be stripped by _first_json
        return _R(
            stdout="Fetching 10 files: 100%\n"
            '{"scope":"federated","projects":["a","b"],"body":"CTX BODY",'
            '"citations":[{"node_id":"x"}],"stats":{"nodes":1}}'
        )

    monkeypatch.setattr(ti.subprocess, "run", fake_run)
    out = ti.federated_ask_tesserae("how does X work?")
    assert out and out["body"] == "CTX BODY"
    assert out["projects"] == ["a", "b"]
    ask_cmd = next(c for c in calls if "ask" in c)
    # federated scope, the FULL alias list, and semantic bridging are passed
    assert "--scope" in ask_cmd and "federated" in ask_cmd
    assert "a" in ask_cmd and "b" in ask_cmd
    assert "--semantic" in ask_cmd


def test_federated_ask_degrades_to_none(monkeypatch):
    # No registered projects (or a failing CLI) → None, never raises.
    monkeypatch.setattr(ti.subprocess, "run", lambda cmd, **kw: _R(returncode=1, stderr="boom"))
    assert ti.federated_ask_tesserae("q") is None


def test_no_semantic_flag_when_disabled(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "list" in cmd:
            return _R(stdout='{"projects":[{"name":"a"}]}')
        return _R(stdout='{"body":"B","projects":["a"],"citations":[],"stats":{}}')

    monkeypatch.setattr(ti.subprocess, "run", fake_run)
    ti.federated_ask_tesserae("q", semantic=False)
    ask_cmd = next(c for c in calls if "ask" in c)
    assert "--no-semantic" in ask_cmd and "--semantic" not in ask_cmd


def test_stream_ideation_injects_grounding_then_streams(monkeypatch):
    monkeypatch.setattr(
        ti,
        "federated_context_message",
        lambda q, **k: {
            "role": "system",
            "content": "GROUNDING",
            "_projects": ["a", "b"],
            "_citations": [1, 2],
        },
    )
    import app.services.conversation_streaming as cs

    captured = {}

    def fake_stream(messages, **kwargs):
        captured["messages"] = messages
        captured["backend"] = kwargs.get("backend")
        yield "Hello "
        yield "world"

    monkeypatch.setattr(cs, "stream_llm_response", fake_stream)

    events = list(sis.stream_ideation([{"role": "user", "content": "an idea"}]))
    kinds = [e for e, _ in events]
    assert kinds[0] == "retrieval" and kinds[-1] == "done"
    assert ("content", {"content": "Hello "}) in events
    assert ("content", {"content": "world"}) in events
    # default backend is a GENERAL model (gemini), not a coding agent
    assert captured["backend"] == "gemini"
    # the grounding system message is inserted BEFORE the latest user message
    msgs = captured["messages"]
    assert any(m.get("content") == "GROUNDING" for m in msgs)
    assert msgs[-1] == {"role": "user", "content": "an idea"}
    # the retrieval frame carries provenance for the UI
    retrieval = next(p for e, p in events if e == "retrieval")
    assert retrieval["projects"] == ["a", "b"] and retrieval["citations"] == 2


def test_stream_ideation_grounding_failure_is_not_fatal(monkeypatch):
    def boom(q, **k):
        raise RuntimeError("tesserae down")

    monkeypatch.setattr(ti, "federated_context_message", boom)
    import app.services.conversation_streaming as cs

    monkeypatch.setattr(cs, "stream_llm_response", lambda messages, **kw: iter(["ok"]))
    events = list(sis.stream_ideation([{"role": "user", "content": "x"}]))
    # still streams a reply; retrieval frame just carries empty provenance
    assert ("content", {"content": "ok"}) in events
    assert [e for e, _ in events][-1] == "done"
    retrieval = next(p for e, p in events if e == "retrieval")
    assert retrieval == {"projects": [], "citations": 0}
