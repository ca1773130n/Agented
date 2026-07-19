"""Regression: a message-bus event evicted by backpressure is re-pended, not lost.

The event was marked 'delivered' on enqueue, so if it's later evicted to make room
for a newer event its DB row stays 'delivered' and the pending-injection path never
recovers it. Eviction must revert the dropped message to 'pending'.
"""

from app.services import agent_message_bus_service as mb


def test_repend_dropped_event_reverts_to_pending(monkeypatch):
    calls = []
    monkeypatch.setattr(mb, "update_message_status", lambda mid, status: calls.append((mid, status)))

    event = mb.AgentMessageBusService._format_sse("message", {"message_id": "msg-1", "content": "hi"})
    mb.AgentMessageBusService._repend_dropped_event(event)

    assert calls == [("msg-1", "pending")]


def test_repend_ignores_unparseable_or_idless_frame(monkeypatch):
    calls = []
    monkeypatch.setattr(mb, "update_message_status", lambda mid, status: calls.append((mid, status)))

    mb.AgentMessageBusService._repend_dropped_event("event: keepalive\ndata: not-json\n\n")
    mb.AgentMessageBusService._repend_dropped_event(
        mb.AgentMessageBusService._format_sse("message", {"content": "no id"})
    )

    assert calls == []  # nothing to re-pend
