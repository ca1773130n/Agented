"""Driver-branch tests for streaming_helper.run_streaming_response (Phase 19-05).

These cover the funnel's 3-way driver branch:

  * cliproxy regression (success criterion 3): a conversational turn resolved
    to ``driver=grd`` must produce a delta sequence BYTE-FOR-BYTE identical to
    the cliproxy baseline — proving the grd-conversational fallthrough reuses
    the unchanged cliproxy block (no duplicate-and-diverge).
  * grd task dispatch (criterion 2): a ``driver=grd`` turn classified as a
    task dispatches ``get_handler('grd_chat').start`` and runs
    ``bridge_psm_to_chat`` — and never calls the cliproxy ``stream_llm_response``.
  * degrade path: when the resolver returns ``cli_agent`` (grd unavailable),
    the cli_agent block runs and the turn is not dropped.
"""

from __future__ import annotations


class _SyncThread:
    """Run the streaming 'thread' body synchronously so the test observes
    the full delta sequence before it returns."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _install_common(monkeypatch, deltas):
    """Stub the funnel's collaborators down to the routing decision so only
    the driver branch is exercised. Captures ChatStateService deltas."""
    import app.services.streaming_helper as sh

    monkeypatch.setattr(sh.threading, "Thread", _SyncThread)

    monkeypatch.setattr(sh.ChatStateService, "init_session", lambda *a, **k: None)
    monkeypatch.setattr(sh.ChatStateService, "push_status", lambda *a, **k: None)
    monkeypatch.setattr(
        sh.ChatStateService,
        "push_delta",
        lambda sid, kind, payload: deltas.append((kind, payload)),
    )

    monkeypatch.setattr(
        sh.SuperAgentSessionService, "assemble_system_prompt", lambda *a, **k: "SYS"
    )
    monkeypatch.setattr(
        sh.SuperAgentSessionService,
        "get_session_state",
        lambda *a, **k: {
            "conversation_log": [{"role": "user", "content": "what is up?"}],
            "project_id": "proj-test",
        },
    )
    monkeypatch.setattr(
        sh.SuperAgentSessionService,
        "add_assistant_message",
        lambda *a, **k: None,
    )


def _force_driver(monkeypatch, value):
    """Pin resolve_execution_driver (imported inside _stream_response) to a
    fixed driver string."""
    from app.services import cli_agent_runner_service as runner

    monkeypatch.setattr(runner, "resolve_execution_driver", lambda *a, **k: value)


def _stub_cliproxy_stream(monkeypatch, chunks):
    """Stub conversation_streaming.stream_llm_response to yield ``chunks``."""
    from app.services import conversation_streaming as cs

    calls = {"n": 0}

    def _fake_stream(*a, **k):
        calls["n"] += 1
        yield from chunks

    monkeypatch.setattr(cs, "stream_llm_response", _fake_stream)
    return calls


def _run(**overrides):
    from app.services.streaming_helper import run_streaming_response

    kwargs = dict(
        session_id="sess-1",
        super_agent_id="sa-1",
        backend="claude",
    )
    kwargs.update(overrides)
    run_streaming_response(**kwargs)


# ---------------------------------------------------------------------------
# 1. cliproxy regression — byte-identical conversational deltas
# ---------------------------------------------------------------------------


def test_grd_conversational_byte_identical_to_cliproxy_baseline(monkeypatch):
    chunks = ["Hello", ", ", "world"]

    # Baseline: driver resolves to cliproxy.
    baseline: list = []
    _install_common(monkeypatch, baseline)
    _force_driver(monkeypatch, "cliproxy")
    _stub_cliproxy_stream(monkeypatch, chunks)
    _run()

    # Candidate: driver resolves to grd, classified conversational → must
    # fall back through the SAME cliproxy block.
    from app.services import turn_classifier_service as tcs

    candidate: list = []
    _install_common(monkeypatch, candidate)
    _force_driver(monkeypatch, "grd")
    monkeypatch.setattr(
        tcs,
        "classify_turn",
        lambda *a, **k: {
            "shape": "conversational",
            "intent": "conversational",
            "grd_command": None,
        },
    )
    _stub_cliproxy_stream(monkeypatch, chunks)
    _run()

    assert candidate == baseline, "grd-conversational deltas must equal cliproxy baseline"
    # And it must actually be the content_delta sequence, not empty.
    assert [d for d in candidate if d[0] == "content_delta"] == [
        ("content_delta", {"content": c}) for c in chunks
    ]


# ---------------------------------------------------------------------------
# 2. grd task dispatch — handler + bridge, no cliproxy stream
# ---------------------------------------------------------------------------


def test_grd_task_dispatches_handler_and_bridge(monkeypatch):
    from app.services import execution_type_handler as eth
    from app.services import grd_chat_bridge as bridge_mod
    from app.services import project_session_manager as psm_mod
    from app.services import turn_classifier_service as tcs

    deltas: list = []
    _install_common(monkeypatch, deltas)
    _force_driver(monkeypatch, "grd")

    monkeypatch.setattr(
        tcs,
        "classify_turn",
        lambda *a, **k: {"shape": "task", "intent": "research", "grd_command": "/grd:research"},
    )

    started = {}

    class _Handler:
        def start(self, cfg):
            started.update(cfg)
            return {"session_id": "grd-sess-9"}

    monkeypatch.setattr(eth, "get_handler", lambda name: _Handler() if name == "grd_chat" else None)

    # subscribe_raw returns a queue draining a single __end__ sentinel.
    from queue import Queue

    q: Queue = Queue()
    q.put(("__end__", {}))
    monkeypatch.setattr(psm_mod.ProjectSessionManager, "subscribe_raw", lambda sid: q)
    unsub = {"called": False}
    monkeypatch.setattr(
        psm_mod.ProjectSessionManager,
        "unsubscribe_raw",
        lambda sid, qq: unsub.update(called=True),
    )

    bridged = {}
    monkeypatch.setattr(
        bridge_mod,
        "bridge_psm_to_chat",
        lambda sid, events, css, **kw: bridged.update(sid=sid, n=len(list(events)), **kw),
    )

    # Guard: cliproxy stream must NOT be called on the task path.
    from app.services import conversation_streaming as cs

    def _boom(*a, **k):
        raise AssertionError("cliproxy stream_llm_response must not run on a grd task turn")
        yield  # pragma: no cover

    monkeypatch.setattr(cs, "stream_llm_response", _boom)

    _run()

    assert started.get("task") == "what is up?"
    assert started.get("grd_command") == "/grd:research"
    assert started.get("project_id") == "proj-test"
    assert bridged.get("sid") == "sess-1"
    assert unsub["called"], "raw subscription must be torn down"


# ---------------------------------------------------------------------------
# 3. degrade path — resolver returns cli_agent, turn not dropped
# ---------------------------------------------------------------------------


def test_cli_agent_driver_takes_runner_path(monkeypatch):
    from app.services import account_rotation_service as ars
    from app.services import cli_agent_runner_service as runner

    deltas: list = []
    _install_common(monkeypatch, deltas)
    _force_driver(monkeypatch, "cli_agent")

    # No real accounts → default-vault single attempt.
    monkeypatch.setattr(ars, "rotation_candidates", lambda *a, **k: [])
    monkeypatch.setattr(runner, "resolve_account_config_dir", lambda *a, **k: None)
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: False)

    ran = {"n": 0}

    def _fake_cli(*a, **k):
        ran["n"] += 1
        yield "agent-reply"

    monkeypatch.setattr(runner, "stream_via_cli_agent", _fake_cli)

    # cliproxy must not run.
    from app.services import conversation_streaming as cs

    def _boom(*a, **k):
        raise AssertionError("cliproxy must not run when driver=cli_agent")
        yield  # pragma: no cover

    monkeypatch.setattr(cs, "stream_llm_response", _boom)

    _run()

    assert ran["n"] == 1, "cli_agent runner path must execute"
    assert ("content_delta", {"content": "agent-reply"}) in deltas
