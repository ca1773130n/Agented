"""Regression: agent message bus SSE queues are bounded and evict empty keys.

An unbounded per-subscriber Queue lets a stalled-but-connected client OOM the
single worker; an un-evicted _subscribers key leaks one entry per agent that
ever connected (orchestration audit C1/C2).
"""

import threading
from queue import Queue

import app.services.agent_message_bus_service as mod
from app.services.agent_message_bus_service import AgentMessageBusService as Bus


def test_subscriber_queue_is_bounded():
    assert Bus._SUBSCRIBER_QUEUE_MAXSIZE > 0


def test_push_drops_oldest_when_full(monkeypatch):
    agent_id = "agent-bp1"
    q: Queue = Queue(maxsize=2)
    q.put("old1")
    q.put("old2")  # now full
    monkeypatch.setattr(Bus, "_subscribers", {agent_id: [q]})
    monkeypatch.setattr(mod, "update_message_status", lambda *a, **k: None)

    Bus._push_to_subscriber(agent_id, "m1", "from", "subj", "content", "normal")

    # Queue stayed bounded (didn't grow past maxsize) and accepted the new event.
    assert q.qsize() == 2
    drained = [q.get_nowait(), q.get_nowait()]
    assert any("content" in d for d in drained)  # newest event present
    assert "old1" not in drained  # oldest was dropped


def test_subscribe_evicts_empty_key():
    agent_id = "agent-bp2"
    gen = Bus.subscribe(agent_id)

    def _drive():
        for _ in gen:  # registers the queue, then blocks on queue.get
            pass

    t = threading.Thread(target=_drive, daemon=True)
    t.start()
    # Wait for registration.
    for _ in range(200):
        if agent_id in Bus._subscribers and Bus._subscribers[agent_id]:
            break
        threading.Event().wait(0.01)
    assert agent_id in Bus._subscribers
    # Signal end-of-stream → generator breaks → finally evicts the empty key.
    Bus._subscribers[agent_id][0].put(None)
    t.join(timeout=5)
    assert agent_id not in Bus._subscribers
