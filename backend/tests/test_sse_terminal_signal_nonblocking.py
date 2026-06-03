"""Regression (Codex review BLOCKER): bounded SSE queues must not deadlock on
the end-of-stream signal. A full queue + blocking put(None) while holding the
lock would hang finalization forever.
"""

from queue import Queue

from app.services.execution_log_service import ExecutionLogService as ELS
from app.services.backend_cli_service import BackendCLIService as BCS


def test_execution_log_signal_end_does_not_block_on_full_queue():
    q: Queue = Queue(maxsize=2)
    q.put("a")
    q.put("b")  # full
    # Must return immediately (drop-oldest), never block.
    ELS._signal_end(q)
    drained = [q.get_nowait(), q.get_nowait()]
    assert None in drained  # terminal sentinel delivered


def test_backend_cli_enqueue_does_not_block_on_full_queue():
    q: Queue = Queue(maxsize=2)
    q.put("a")
    q.put("b")  # full
    BCS._enqueue(q, None)
    assert q.qsize() == 2  # stayed bounded
    drained = [q.get_nowait(), q.get_nowait()]
    assert None in drained
