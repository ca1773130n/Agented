"""bridge_psm_to_chat tests (19-04, REQ-11).

Verifies the PSM stream-json -> chat-SSE mapping preserves event
order, terminates with the right status, and emits the exact frontend
WIRE strings (content_delta / tool_use / finish / error) — never the
ChatDeltaType enum name 'tool_call'.
"""

from app.services.grd_chat_bridge import bridge_psm_to_chat


class FakeChatState:
    """Records push_delta / push_status calls in order."""

    def __init__(self):
        self.deltas = []  # list[(delta_type, data)]
        self.statuses = []  # list[status]

    def push_delta(self, session_id, delta_type, data=None):
        self.deltas.append((delta_type, data))

    def push_status(self, session_id, status):
        self.statuses.append(status)


def test_ordering_text_text_tool_result():
    events = [
        {"type": "text", "content": "Hello "},
        {"type": "text", "content": "world"},
        {"type": "tool_use", "name": "Edit", "input": {"path": "a.py"}},
        {"type": "result", "finish_reason": "stop"},
    ]
    cs = FakeChatState()
    bridge_psm_to_chat("sess-1", events, cs)

    types = [d[0] for d in cs.deltas]
    assert types == ["content_delta", "content_delta", "tool_use", "finish"]
    assert cs.deltas[0][1] == {"content": "Hello "}
    assert cs.deltas[1][1] == {"content": "world"}
    assert cs.deltas[2][1] == {"name": "Edit", "input": {"path": "a.py"}}
    assert cs.deltas[3][1] == {"finish_reason": "stop"}
    assert cs.statuses == ["complete"]


def test_wire_strings_not_enum_names():
    # Tool blocks MUST map to the wire string 'tool_use', NOT 'tool_call'.
    events = [{"type": "tool_use", "name": "Bash"}, {"type": "result"}]
    cs = FakeChatState()
    bridge_psm_to_chat("s", events, cs)
    emitted = {d[0] for d in cs.deltas}
    assert "tool_use" in emitted
    assert "tool_call" not in emitted
    # All emitted types are exactly the four wire strings.
    assert emitted <= {"content_delta", "tool_use", "finish", "error"}


def test_error_propagation():
    events = [
        {"type": "text", "content": "partial"},
        {"type": "error", "error_message": "boom"},
    ]
    cs = FakeChatState()
    bridge_psm_to_chat("sess-err", events, cs)

    types = [d[0] for d in cs.deltas]
    assert types == ["content_delta", "error"]
    assert cs.deltas[1] == ("error", {"error_message": "boom"})
    assert cs.statuses == ["error"]


def test_error_terminates_stream():
    # Events after an error must NOT be processed.
    events = [
        {"type": "error", "error": "fail"},
        {"type": "text", "content": "should not appear"},
    ]
    cs = FakeChatState()
    bridge_psm_to_chat("s", events, cs)
    assert [d[0] for d in cs.deltas] == ["error"]
    assert cs.statuses == ["error"]


def test_synthetic_finish_when_source_drains():
    # No terminal marker -> bridge emits a finish + complete so the
    # frontend stream closes cleanly.
    events = [{"type": "text", "content": "hi"}]
    cs = FakeChatState()
    bridge_psm_to_chat("s", events, cs)
    assert [d[0] for d in cs.deltas] == ["content_delta", "finish"]
    assert cs.statuses == ["complete"]


def test_finish_carries_backend_and_stream_model():
    # The finish delta must label the bubble with the answering backend +
    # model; a model from the stream's assistant event wins over the fallback.
    events = [
        {"type": "assistant", "message": {"model": "claude-sonnet-4-20250514"}, "content": "hi"},
        {"type": "result", "finish_reason": "stop"},
    ]
    cs = FakeChatState()
    bridge_psm_to_chat("s", events, cs, backend="claude", model="sonnet-4")
    finish = cs.deltas[-1]
    assert finish[0] == "finish"
    assert finish[1]["backend"] == "claude"
    assert finish[1]["model"] == "claude-sonnet-4-20250514"


def test_finish_uses_fallback_model_when_stream_has_none():
    events = [{"type": "text", "content": "hi"}, {"type": "result"}]
    cs = FakeChatState()
    bridge_psm_to_chat("s", events, cs, backend="claude", model="sonnet-4")
    finish = cs.deltas[-1][1]
    assert finish["backend"] == "claude"
    assert finish["model"] == "sonnet-4"
