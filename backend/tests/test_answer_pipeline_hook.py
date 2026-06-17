"""Tests for Task 3: Hook into the leader turn.

Verifies that run_streaming_response with rag_enabled=True:
1. Calls gather_context and inserts context BEFORE the final user message.
2. Pushes planning + retrieval deltas.
3. Fails open when gather raises.
4. Does NOT call gather when rag_enabled=False (default).
5. Persists facts + pushes citations delta after finish.
6. chat_retry_service._dispatch recomputes rag_enabled/rag_project_id for leader sessions.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helpers — mirror test_streaming_helper_rotation._install_common_stubs
# ---------------------------------------------------------------------------


def _install_common_stubs(monkeypatch, deltas, *, captured_llm_messages=None):
    """Stub collaborators so the RAG hook is the sole variable.

    Forces the CLIProxy path (use_cli_agent=False via should_route_via_cli_agent).
    Captures ChatStateService deltas into `deltas`.
    Captures the messages list passed to stream_llm_response when
    captured_llm_messages is a list (appends the messages list in-place).
    """
    import app.services.streaming_helper as sh
    from app.services import cli_agent_runner_service as runner
    from app.services import conversation_streaming as cs

    # Run the streaming "thread" synchronously.
    class _SyncThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(sh.threading, "Thread", _SyncThread)

    # ChatStateService capture.
    monkeypatch.setattr(sh.ChatStateService, "init_session", lambda *a, **k: None)
    monkeypatch.setattr(sh.ChatStateService, "push_status", lambda *a, **k: None)
    monkeypatch.setattr(
        sh.ChatStateService,
        "push_delta",
        lambda sid, kind, payload: deltas.append((kind, payload)),
    )

    # Session service: minimal system prompt + one user message in log.
    monkeypatch.setattr(
        sh.SuperAgentSessionService, "assemble_system_prompt", lambda *a, **k: "SYS"
    )
    monkeypatch.setattr(
        sh.SuperAgentSessionService,
        "get_session_state",
        lambda *a, **k: {
            "conversation_log": [{"role": "user", "content": "What is the project status?"}]
        },
    )
    monkeypatch.setattr(
        sh.SuperAgentSessionService,
        "add_assistant_message",
        lambda sid, content, backend=None, model=None: None,
    )

    # Force CLIProxy path — not the CLI agent runner. The funnel resolves the
    # driver via resolve_execution_driver (19-05), so pin that to "cliproxy".
    monkeypatch.setattr(runner, "resolve_execution_driver", lambda *a, **k: "cliproxy")

    # Stub stream_llm_response to yield a simple answer and record messages.
    def _fake_stream(messages, **kwargs):
        if captured_llm_messages is not None:
            captured_llm_messages.append(list(messages))  # snapshot
        yield "The answer is 42."

    monkeypatch.setattr(cs, "stream_llm_response", _fake_stream)

    # drop_empty_content_messages — identity passthrough.
    import app.services.conversation_filters as cf

    monkeypatch.setattr(cf, "drop_empty_content_messages", lambda msgs: msgs)

    # backends.update_backend_last_used — no-op.
    try:
        from app.db import backends as dbb

        monkeypatch.setattr(dbb, "update_backend_last_used", lambda *a, **k: None)
    except Exception:
        pass

    # Per-project corpus-health gate: default to HEALTHY so the RAG hook runs.
    # Tests that exercise the thin-corpus skip override this afterwards.
    import app.services.answer_pipeline_service as aps

    monkeypatch.setattr(
        aps,
        "corpus_health",
        lambda *a, **k: {
            "healthy": True,
            "total": 99,
            "kg_signals": 99,
            "takeaways": 0,
            "executions": 0,
            "min_items": 8,
        },
    )


# ---------------------------------------------------------------------------
# Test 1: rag_enabled=False (default) → gather NOT called
# ---------------------------------------------------------------------------


def test_rag_disabled_does_not_call_gather(monkeypatch, isolated_db):
    import app.services.streaming_helper as sh

    deltas: list = []
    _install_common_stubs(monkeypatch, deltas)

    gather_called = []

    import app.services.answer_pipeline_service as aps

    monkeypatch.setattr(
        aps,
        "gather_context",
        lambda *a, **k: (
            gather_called.append(1)
            or {
                "chunks": [],
                "context_message": None,
                "iterations": 1,
                "sufficient": True,
                "gap": None,
            }
        ),
    )

    sh.run_streaming_response(
        session_id="sess-rag-off",
        super_agent_id="sa-1",
        backend="claude",
        # rag_enabled not passed — defaults to False
    )

    assert not gather_called, "gather_context must NOT be called when rag_enabled=False"
    kinds = [k for k, _ in deltas]
    assert "finish" in kinds


# ---------------------------------------------------------------------------
# Test 2: rag_enabled=True → gather called; context inserted BEFORE final user msg
# ---------------------------------------------------------------------------


def test_rag_enabled_context_inserted_before_user_message(monkeypatch, isolated_db):
    import app.services.answer_pipeline_service as aps
    import app.services.streaming_helper as sh

    deltas: list = []
    captured_messages: list = []  # will capture the messages list passed to stream_llm_response
    _install_common_stubs(monkeypatch, deltas, captured_llm_messages=captured_messages)

    ctx_msg = {"role": "system", "content": "[F1] (takeaway, takeaway:t1) relevant context here"}

    monkeypatch.setattr(
        aps,
        "gather_context",
        lambda project_id, turn, **kw: {
            "chunks": [
                aps.RetrievedChunk(
                    text="relevant context here",
                    source="takeaway",
                    provenance_key="takeaway:t1",
                    score=0.9,
                )
            ],
            "context_message": ctx_msg,
            "iterations": 1,
            "sufficient": True,
            "gap": None,
        },
    )

    # Stub extract_facts_from_answer to return empty list.
    monkeypatch.setattr(aps, "extract_facts_from_answer", lambda *a, **k: [])
    # Stub insert_facts.
    from app.db import extracted_facts as ef

    monkeypatch.setattr(ef, "insert_facts", lambda *a, **k: 0)

    sh.run_streaming_response(
        session_id="sess-rag-on",
        super_agent_id="sa-1",
        backend="claude",
        rag_enabled=True,
        rag_project_id="proj-abc",
    )

    kinds = [k for k, _ in deltas]

    # planning + retrieval deltas pushed
    assert "planning" in kinds, f"expected 'planning' delta, got: {kinds}"
    assert "retrieval" in kinds, f"expected 'retrieval' delta, got: {kinds}"
    assert "finish" in kinds

    # messages[-1] is the user turn; messages[-2] is the RAG context
    assert captured_messages, "stream_llm_response was not called"
    sent = captured_messages[0]
    assert len(sent) >= 3, f"expected ≥3 messages (system, ctx, user) but got {sent}"
    assert sent[-1]["role"] == "user", f"last msg must be user, got {sent[-1]}"
    assert sent[-2] == ctx_msg, f"second-to-last message must be the RAG context, got {sent[-2]}"


# ---------------------------------------------------------------------------
# Test 3: gather raises → fail-open, no exception escapes
# ---------------------------------------------------------------------------


def test_rag_gather_raises_fails_open(monkeypatch, isolated_db):
    import app.services.answer_pipeline_service as aps
    import app.services.streaming_helper as sh

    deltas: list = []
    captured_messages: list = []
    _install_common_stubs(monkeypatch, deltas, captured_llm_messages=captured_messages)

    monkeypatch.setattr(
        aps,
        "gather_context",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pipeline exploded")),
    )

    sh.run_streaming_response(
        session_id="sess-rag-fail",
        super_agent_id="sa-1",
        backend="claude",
        rag_enabled=True,
        rag_project_id="proj-abc",
    )

    kinds = [k for k, _ in deltas]
    # Turn must still proceed normally — finish should arrive.
    assert "finish" in kinds, f"expected finish even after gather failure, got: {kinds}"
    # No context message inserted — gather failed so baseline path used.
    assert captured_messages, "stream_llm_response should still be called"
    sent = captured_messages[0]
    # The second-to-last should NOT be the ctx message (it was never inserted).
    for msg in sent:
        assert msg.get("content") != "[F1] (takeaway, takeaway:t1) relevant context here"


# ---------------------------------------------------------------------------
# Test 4: facts persisted + citations delta after finish
# ---------------------------------------------------------------------------


def test_facts_persisted_and_citations_delta_pushed(monkeypatch, isolated_db):
    import app.services.answer_pipeline_service as aps
    import app.services.streaming_helper as sh

    deltas: list = []
    _install_common_stubs(monkeypatch, deltas)

    chunk = aps.RetrievedChunk(
        text="relevant context here",
        source="takeaway",
        provenance_key="takeaway:t1",
        score=0.9,
    )
    ctx_msg = {"role": "system", "content": "[F1] (takeaway, takeaway:t1) relevant context here"}

    monkeypatch.setattr(
        aps,
        "gather_context",
        lambda project_id, turn, **kw: {
            "chunks": [chunk],
            "context_message": ctx_msg,
            "iterations": 1,
            "sufficient": True,
            "gap": None,
        },
    )

    extracted = [{"claim": "The answer is 42.", "evidence": ["takeaway:t1"], "confidence": 0.9}]
    monkeypatch.setattr(aps, "extract_facts_from_answer", lambda *a, **k: extracted)

    inserted: list = []
    from app.db import extracted_facts as ef

    monkeypatch.setattr(
        ef,
        "insert_facts",
        lambda session_id, *, super_agent_id, project_id, facts: (
            inserted.extend(facts) or len(facts)
        ),
    )

    sh.run_streaming_response(
        session_id="sess-cites",
        super_agent_id="sa-1",
        backend="claude",
        rag_enabled=True,
        rag_project_id="proj-abc",
    )

    kinds = [k for k, _ in deltas]
    assert "finish" in kinds, kinds

    # citations delta must appear AFTER finish
    finish_idx = next(i for i, (k, _) in enumerate(deltas) if k == "finish")
    cite_entries = [(i, p) for i, (k, p) in enumerate(deltas) if k == "citations"]
    assert cite_entries, f"expected 'citations' delta, got: {kinds}"
    cite_idx, cite_payload = cite_entries[0]
    assert cite_idx > finish_idx, "citations delta must arrive AFTER finish"

    # Payload shape
    assert cite_payload["message_scope"] == "last_assistant"
    assert len(cite_payload["citations"]) == 1
    assert cite_payload["citations"][0]["kind"] == "takeaway"
    assert cite_payload["citations"][0]["value"] == "takeaway:t1"
    assert cite_payload["facts"] == extracted

    # Facts were persisted
    assert inserted == extracted


# ---------------------------------------------------------------------------
# Test 4b: thin corpus → per-project gate skips the pipeline entirely
# ---------------------------------------------------------------------------


def test_rag_thin_corpus_skips_pipeline(monkeypatch, isolated_db):
    import app.services.answer_pipeline_service as aps
    import app.services.streaming_helper as sh

    deltas: list = []
    _install_common_stubs(monkeypatch, deltas)

    # Override the default healthy stub with an UNHEALTHY corpus.
    monkeypatch.setattr(
        aps,
        "corpus_health",
        lambda *a, **k: {
            "healthy": False,
            "total": 3,
            "kg_signals": 3,
            "takeaways": 0,
            "executions": 0,
            "min_items": 8,
        },
    )

    gather_called: list = []
    monkeypatch.setattr(
        aps,
        "gather_context",
        lambda *a, **k: (
            gather_called.append(1)
            or {
                "chunks": [],
                "context_message": None,
                "iterations": 1,
                "sufficient": True,
                "gap": None,
            }
        ),
    )

    sh.run_streaming_response(
        session_id="sess-thin",
        super_agent_id="sa-1",
        backend="claude",
        rag_enabled=True,
        rag_project_id="proj-thin",
    )

    kinds = [k for k, _ in deltas]
    assert not gather_called, "pipeline must be skipped for a thin corpus"
    assert "planning" not in kinds, "no planning delta when the pipeline is skipped"
    skip_deltas = [p for k, p in deltas if k == "retrieval" and p.get("skipped") == "thin_corpus"]
    assert skip_deltas, f"expected a thin_corpus skip delta, got: {deltas}"
    assert skip_deltas[0]["corpus_items"] == 3
    assert "finish" in kinds, "baseline turn must still complete"


# ---------------------------------------------------------------------------
# Test 5: chat_retry_service._dispatch recomputes rag params for leader sessions
# ---------------------------------------------------------------------------


def test_retry_dispatch_passes_rag_for_leader_session(monkeypatch, isolated_db):
    """A parked leader-session retry re-dispatches with rag_enabled=True."""
    from app.services import chat_retry_service as crs
    from app.services import streaming_helper as sh

    # Stub get_super_agent_session inside the db module that _dispatch imports.
    leader_session = {
        "id": "sess-leader",
        "session_type": "leader",
        "project_id": "proj-leader",
        "super_agent_id": "sa-leader",
    }
    from app.db import super_agents as sa_mod

    monkeypatch.setattr(sa_mod, "get_super_agent_session", lambda session_id: leader_session)

    # Capture run_streaming_response call kwargs.
    calls: list = []
    monkeypatch.setattr(
        sh,
        "run_streaming_response",
        lambda **kw: calls.append(kw),
    )

    row = {
        "session_id": "sess-leader",
        "super_agent_id": "sa-leader",
        "backend": "claude",
        "account_id": None,
        "model": None,
        "cwd": None,
        "chat_mode": None,
        "instance_id": None,
        "use_cli_agent": None,
    }

    # Stub ChatStateService.push_delta to avoid session-not-found errors.
    from app.services.chat_state_service import ChatStateService

    monkeypatch.setattr(ChatStateService, "push_delta", lambda *a, **k: None)

    crs.ChatRetryService._dispatch(row, next_attempts=1)

    assert calls, "run_streaming_response was not called"
    kw = calls[0]
    assert kw.get("rag_enabled") is True, f"expected rag_enabled=True, got {kw}"
    assert kw.get("rag_project_id") == "proj-leader", (
        f"expected rag_project_id='proj-leader', got {kw}"
    )
