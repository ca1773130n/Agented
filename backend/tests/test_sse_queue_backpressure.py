"""Regression: bounded SSE subscriber queues drop oldest instead of OOMing.

A stalled SSE client (backgrounded tab / slow link) whose queue never drains must
not grow unbounded and OOM the single gunicorn worker. The subscriber queues are
now bounded and use drop-oldest backpressure, mirroring ExecutionLogService.
"""

from queue import Queue

from app.services.chat_state_service import ChatStateService
from app.services.project_session_manager import ProjectSessionManager


def test_chat_state_offer_drops_oldest_when_full():
    q: Queue = Queue(maxsize=2)
    ChatStateService._offer(q, "a")
    ChatStateService._offer(q, "b")
    ChatStateService._offer(q, "c")  # full -> drop oldest "a"
    assert q.qsize() == 2
    assert [q.get_nowait(), q.get_nowait()] == ["b", "c"]


def test_psm_offer_drops_oldest_when_full():
    q: Queue = Queue(maxsize=2)
    ProjectSessionManager._offer(q, "x")
    ProjectSessionManager._offer(q, "y")
    ProjectSessionManager._offer(q, "z")
    assert q.qsize() == 2
    assert [q.get_nowait(), q.get_nowait()] == ["y", "z"]


def test_terminal_sentinel_always_delivered_on_full_queue():
    """The None / __end__ sentinel that stops the reader must get in even when the
    queue is full — drop-oldest frees a slot, so the generator never hangs."""
    q: Queue = Queue(maxsize=2)
    ProjectSessionManager._offer(q, "1")
    ProjectSessionManager._offer(q, "2")
    ProjectSessionManager._offer(q, None)  # full -> drop "1", deliver sentinel
    drained = [q.get_nowait(), q.get_nowait()]
    assert None in drained


def test_subscriber_queues_are_bounded():
    assert ProjectSessionManager._SUBSCRIBER_QUEUE_MAXSIZE > 0
    assert ChatStateService._SUBSCRIBER_QUEUE_MAXSIZE > 0
