"""Tests for the execution_events decoupling channel (PR-Q).

The channel sits between WorkflowExecutionService (emitter) and
WorkflowTriggerService (registered handler). Verifies:
- handlers fire on emit, in registration order
- duplicate registration is idempotent
- per-handler exceptions are swallowed; other handlers still run
- clear_completion_handlers wipes the registry
"""

from __future__ import annotations

import pytest

from app.services import execution_events


@pytest.fixture(autouse=True)
def _isolate_handlers():
    """Each test starts with an empty registry and restores it."""
    execution_events.clear_completion_handlers()
    yield
    execution_events.clear_completion_handlers()


def test_register_and_emit_fires_handler():
    seen: list[tuple] = []

    def handler(entity_type, entity_id, status, output):
        seen.append((entity_type, entity_id, status, output))

    execution_events.register_completion_handler(handler)
    execution_events.emit_execution_complete("workflow", "wf-1", "completed", {"k": "v"})

    assert seen == [("workflow", "wf-1", "completed", {"k": "v"})]


def test_register_is_idempotent():
    """Re-registering the same callable doesn't queue it twice."""
    calls = []

    def handler(*args):
        calls.append(args)

    execution_events.register_completion_handler(handler)
    execution_events.register_completion_handler(handler)
    execution_events.emit_execution_complete("workflow", "wf-1", "completed", None)

    assert len(calls) == 1


def test_handlers_fire_in_registration_order():
    order: list[str] = []

    execution_events.register_completion_handler(lambda *_: order.append("first"))
    execution_events.register_completion_handler(lambda *_: order.append("second"))
    execution_events.register_completion_handler(lambda *_: order.append("third"))

    execution_events.emit_execution_complete("workflow", "wf-1", "completed", None)

    assert order == ["first", "second", "third"]


def test_handler_exception_is_swallowed_other_handlers_still_fire(caplog):
    """A buggy handler can't break the chain."""
    seen: list[str] = []

    def first(*_):
        raise RuntimeError("boom")

    def second(*_):
        seen.append("ran")

    execution_events.register_completion_handler(first)
    execution_events.register_completion_handler(second)

    with caplog.at_level("ERROR"):
        execution_events.emit_execution_complete("workflow", "wf-1", "failed", None)

    assert seen == ["ran"]
    assert any("execution_events handler" in r.message for r in caplog.records)


def test_clear_removes_all_handlers():
    execution_events.register_completion_handler(lambda *_: None)
    execution_events.clear_completion_handlers()

    seen: list[str] = []
    execution_events.register_completion_handler(lambda *_: seen.append("ran"))
    execution_events.emit_execution_complete("workflow", "wf-1", "completed", None)

    assert seen == ["ran"]


def test_workflow_execution_service_no_longer_imports_trigger_service():
    """Hot path source must NOT reference workflow_trigger_service.

    Before PR-Q, ``_run_workflow`` did a lazy
    ``from .workflow_trigger_service import WorkflowTriggerService`` which
    completed the two-way runtime cycle codex F7 flagged. After PR-Q the
    file only references the execution_events channel.
    """
    import inspect

    from app.services import workflow_execution_service

    src = inspect.getsource(workflow_execution_service)
    assert "workflow_trigger_service" not in src, (
        "workflow_execution_service must use execution_events instead of "
        "directly importing workflow_trigger_service"
    )
    assert "emit_execution_complete" in src
