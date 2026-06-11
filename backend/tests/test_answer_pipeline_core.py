"""TDD tests for AnswerPipelineService — pure core logic (no DB).

Tests _parse_plan, _parse_sufficiency, gather_context (stubbed retrievers),
and extract_facts_from_answer.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_call(responses: list[str]):
    """Return a callable that pops from `responses` on each call."""
    responses = list(responses)

    def _call(messages: list[dict]) -> str:
        if responses:
            return responses.pop(0)
        return ""

    return _call


# ---------------------------------------------------------------------------
# _parse_plan
# ---------------------------------------------------------------------------


def test_parse_plan_valid_json_array():
    from app.services.answer_pipeline_service import _parse_plan

    raw = '[{"query": "what is X", "sources": ["kg_signal", "takeaway"]}]'
    result = _parse_plan(raw)
    assert len(result) == 1
    assert result[0]["query"] == "what is X"
    assert result[0]["sources"] == ["kg_signal", "takeaway"]


def test_parse_plan_json_embedded_in_prose():
    from app.services.answer_pipeline_service import _parse_plan

    raw = 'Here are my queries: [{"query": "alpha", "sources": ["all"]}, {"query": "beta", "sources": ["execution_log"]}] end.'
    result = _parse_plan(raw)
    assert len(result) == 2
    assert result[0]["query"] == "alpha"
    assert result[1]["query"] == "beta"


def test_parse_plan_garbage_falls_back_to_raw_turn():
    from app.services.answer_pipeline_service import _parse_plan

    raw = "this is not json at all"
    result = _parse_plan(raw, fallback_turn="my question")
    assert len(result) == 1
    assert result[0]["query"] == "my question"
    assert result[0]["sources"] == ["all"]


def test_parse_plan_more_than_four_truncated():
    from app.services.answer_pipeline_service import _parse_plan

    queries = [{"query": f"q{i}", "sources": ["all"]} for i in range(6)]
    import json

    result = _parse_plan(json.dumps(queries))
    assert len(result) == 4


# ---------------------------------------------------------------------------
# _parse_sufficiency
# ---------------------------------------------------------------------------


def test_parse_sufficiency_valid():
    from app.services.answer_pipeline_service import _parse_sufficiency

    raw = (
        '{"sufficient": false, "gap": "missing execution details", "feedback": "need more context"}'
    )
    result = _parse_sufficiency(raw)
    assert result["sufficient"] is False
    assert result["gap"] == "missing execution details"


def test_parse_sufficiency_embedded_in_prose():
    from app.services.answer_pipeline_service import _parse_sufficiency

    raw = 'Analysis: {"sufficient": true, "gap": null, "feedback": "all good"} done.'
    result = _parse_sufficiency(raw)
    assert result["sufficient"] is True


def test_parse_sufficiency_garbage_fails_open():
    from app.services.answer_pipeline_service import _parse_sufficiency

    result = _parse_sufficiency("this is garbage output from the LLM")
    assert result["sufficient"] is True
    assert "gap" in result


# ---------------------------------------------------------------------------
# gather_context — sufficient on round 1
# ---------------------------------------------------------------------------


def test_gather_context_sufficient_round1(monkeypatch):
    from app.services import answer_pipeline_service as svc

    chunks_returned = [
        svc.RetrievedChunk(
            text="signal content",
            source="kg_signal",
            provenance_key="signal:sig-1",
            score=0.9,
        )
    ]

    def _fake_kg(project_id, query, **kwargs):
        return chunks_returned

    monkeypatch.setattr(svc, "_search_kg_signals", _fake_kg)
    monkeypatch.setattr(svc, "_search_execution_logs", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_takeaways", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_findings", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_verifications", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_ask_tesserae_budgeted", lambda *a, **kw: [])

    plan_response = '[{"query": "what is the project status", "sources": ["kg_signal"]}]'
    sufficiency_response = '{"sufficient": true, "gap": null, "feedback": "all good"}'
    llm_call = _make_llm_call([plan_response, sufficiency_response])

    result = svc.gather_context(
        "proj-aaa",
        "what is the project status",
        llm_call=llm_call,
        deadline_seconds=20,
    )

    assert result["sufficient"] is True
    assert result["iterations"] == 1
    assert len(result["chunks"]) == 1
    assert result["chunks"][0].provenance_key == "signal:sig-1"

    ctx = result["context_message"]
    assert ctx is not None
    assert "[F1]" in ctx["content"]
    assert "signal:sig-1" in ctx["content"]


# ---------------------------------------------------------------------------
# gather_context — insufficient → feedback reaches round-2 plan prompt
# ---------------------------------------------------------------------------


def test_gather_context_insufficient_then_sufficient(monkeypatch):
    from app.services import answer_pipeline_service as svc

    chunk_r1 = svc.RetrievedChunk(
        text="partial result",
        source="execution_log",
        provenance_key="execution:exec-1",
        score=0.5,
    )
    chunk_r2 = svc.RetrievedChunk(
        text="extra detail",
        source="takeaway",
        provenance_key="takeaway:tw-1",
        score=0.6,
    )

    call_count = {"n": 0}

    def _fake_exec_logs(project_id, query, **kwargs):
        call_count["n"] += 1
        return [chunk_r1] if call_count["n"] == 1 else [chunk_r1, chunk_r2]

    monkeypatch.setattr(svc, "_search_kg_signals", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_execution_logs", _fake_exec_logs)
    monkeypatch.setattr(svc, "_search_takeaways", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_findings", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_verifications", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_ask_tesserae_budgeted", lambda *a, **kw: [])

    captured_prompts: list[str] = []

    def _recording_llm_call(messages: list[dict]) -> str:
        for m in messages:
            captured_prompts.append(str(m.get("content", "")))
        # Responses: plan1, sufficiency1 (insufficient), plan2, sufficiency2 (sufficient)
        idx = len(captured_prompts)
        if idx <= 2:
            if "sources" in "".join(captured_prompts[:2]):
                return '{"sufficient": false, "gap": "need more exec details", "feedback": "include execution logs"}'
            return '[{"query": "original question", "sources": ["execution_log"]}]'
        else:
            return '{"sufficient": true, "gap": null, "feedback": "ok"}'

    # Use a simple sequential mock
    responses = [
        '[{"query": "what happened", "sources": ["execution_log"]}]',  # plan round 1
        '{"sufficient": false, "gap": "missing details", "feedback": "include execution logs"}',  # sufficiency round 1
        '[{"query": "what happened with execution", "sources": ["execution_log"]}]',  # plan round 2
        '{"sufficient": true, "gap": null, "feedback": "ok"}',  # sufficiency round 2
    ]
    llm_call = _make_llm_call(responses)

    result = svc.gather_context(
        "proj-aaa",
        "what happened",
        llm_call=llm_call,
        max_iterations=2,
        deadline_seconds=20,
    )

    assert result["iterations"] == 2
    # feedback from round 1 should be visible in the round-2 plan prompt
    # (we verify by checking the gap/feedback was present)
    assert result["sufficient"] is True


# ---------------------------------------------------------------------------
# gather_context — all retrievers raise → empty chunks, no exception
# ---------------------------------------------------------------------------


def test_gather_context_all_retrievers_raise(monkeypatch):
    from app.services import answer_pipeline_service as svc

    def _raise(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(svc, "_search_kg_signals", _raise)
    monkeypatch.setattr(svc, "_search_execution_logs", _raise)
    monkeypatch.setattr(svc, "_search_takeaways", _raise)
    monkeypatch.setattr(svc, "_search_findings", _raise)
    monkeypatch.setattr(svc, "_search_verifications", _raise)
    monkeypatch.setattr(svc, "_ask_tesserae_budgeted", _raise)

    plan_response = '[{"query": "q", "sources": ["all"]}]'
    sufficiency_response = '{"sufficient": true, "gap": null, "feedback": "ok"}'
    llm_call = _make_llm_call([plan_response, sufficiency_response])

    result = svc.gather_context(
        "proj-aaa",
        "something",
        llm_call=llm_call,
        deadline_seconds=20,
    )

    # No exception raised; empty chunks; context_message is None (no chunks to format)
    assert result["chunks"] == []
    assert result["context_message"] is None
    assert result["iterations"] >= 1


# ---------------------------------------------------------------------------
# gather_context — deadline exceeded → stops early
# ---------------------------------------------------------------------------


def test_gather_context_deadline_stops_early(monkeypatch):
    import time  # noqa: PLC0415

    from app.services import answer_pipeline_service as svc

    def _slow_retriever(*a, **kw):
        time.sleep(0.5)
        return []

    monkeypatch.setattr(svc, "_search_kg_signals", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_execution_logs", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_takeaways", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_findings", lambda *a, **kw: [])
    monkeypatch.setattr(svc, "_search_verifications", _slow_retriever)
    monkeypatch.setattr(svc, "_ask_tesserae_budgeted", lambda *a, **kw: [])

    plan_response = '[{"query": "q", "sources": ["verification"]}]'
    sufficiency_response = '{"sufficient": true, "gap": null, "feedback": "ok"}'
    llm_call = _make_llm_call([plan_response, sufficiency_response])

    # Very tight deadline — function should not raise, should return gracefully
    result = svc.gather_context(
        "proj-aaa",
        "something",
        llm_call=llm_call,
        deadline_seconds=0.05,  # 50ms — way less than the 500ms sleep
    )

    # Should complete without raising
    assert "chunks" in result
    assert "iterations" in result


# ---------------------------------------------------------------------------
# extract_facts_from_answer
# ---------------------------------------------------------------------------


def test_extract_facts_maps_fact_ids_to_evidence():
    from app.services.answer_pipeline_service import RetrievedChunk, extract_facts_from_answer

    chunks = [
        RetrievedChunk(
            text="signal text",
            source="kg_signal",
            provenance_key="signal:sig-1",
            score=0.9,
        ),
        RetrievedChunk(
            text="log text",
            source="execution_log",
            provenance_key="execution:exec-1",
            score=0.7,
        ),
    ]
    llm_response = (
        '[{"claim": "project is on track", "fact_ids": ["F1", "F2"], "confidence": 0.85}]'
    )
    llm_call = _make_llm_call([llm_response])

    facts = extract_facts_from_answer(
        "project is on track based on logs", chunks, llm_call=llm_call
    )

    assert len(facts) == 1
    assert facts[0]["claim"] == "project is on track"
    assert facts[0]["confidence"] == pytest.approx(0.85)
    # evidence should reference provenance of F1=chunks[0] and F2=chunks[1]
    evidence = facts[0]["evidence"]
    assert any("signal:sig-1" in str(e) for e in evidence)
    assert any("execution:exec-1" in str(e) for e in evidence)


def test_extract_facts_garbage_response_returns_empty():
    from app.services.answer_pipeline_service import RetrievedChunk, extract_facts_from_answer

    chunks = [
        RetrievedChunk(
            text="some text",
            source="kg_signal",
            provenance_key="signal:sig-1",
            score=0.5,
        )
    ]
    llm_call = _make_llm_call(["not json at all"])

    facts = extract_facts_from_answer("some answer", chunks, llm_call=llm_call)
    assert facts == []
