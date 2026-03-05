"""Tests for execution queue: enqueue, dispatcher, concurrency, FIFO ordering, circuit breaker."""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.db.execution_queue import (
    cancel_pending_entries,
    count_active_for_trigger,
    enqueue_execution,
    get_pending_entries,
    get_queue_depth,
    get_queue_summary,
    reset_stale_dispatching,
    update_entry_status,
)
from app.services.execution_queue_service import (
    MAX_QUEUE_DEPTH_PER_TRIGGER,
    ExecutionQueueService,
    QueueFullError,
)


@pytest.fixture(autouse=True)
def _reset_queue_service():
    """Reset ExecutionQueueService state between tests."""
    ExecutionQueueService.reset()
    yield
    ExecutionQueueService.reset()


# --- DB module tests ---


class TestExecutionQueueDB:
    """Test execution_queue CRUD operations."""

    def test_enqueue_adds_entry(self, isolated_db):
        """Enqueue creates a pending entry in the queue table."""
        entry_id = enqueue_execution("trig-abc", "webhook", "hello", "{}")
        assert entry_id.startswith("qe-")

        entries = get_pending_entries()
        assert len(entries) == 1
        assert entries[0]["id"] == entry_id
        assert entries[0]["trigger_id"] == "trig-abc"
        assert entries[0]["trigger_type"] == "webhook"
        assert entries[0]["status"] == "pending"

    def test_fifo_ordering(self, isolated_db):
        """Entries are returned in FIFO order (priority DESC, created_at ASC)."""
        id_a = enqueue_execution("trig-abc", "webhook", "A", "{}")
        id_b = enqueue_execution("trig-abc", "webhook", "B", "{}")
        id_c = enqueue_execution("trig-abc", "webhook", "C", "{}")

        entries = get_pending_entries()
        assert len(entries) == 3
        assert entries[0]["id"] == id_a
        assert entries[1]["id"] == id_b
        assert entries[2]["id"] == id_c

    def test_priority_ordering(self, isolated_db):
        """Higher priority entries are dispatched first."""
        id_low = enqueue_execution("trig-abc", "webhook", "low", "{}", priority=0)
        id_high = enqueue_execution("trig-abc", "webhook", "high", "{}", priority=10)

        entries = get_pending_entries()
        assert entries[0]["id"] == id_high
        assert entries[1]["id"] == id_low

    def test_update_status_cas(self, isolated_db):
        """CAS update only succeeds when expected status matches."""
        entry_id = enqueue_execution("trig-abc", "webhook", "test", "{}")

        # Should succeed: pending -> dispatching
        assert update_entry_status(entry_id, "dispatching", expected_status="pending")

        # Should fail: trying pending -> completed but it's already dispatching
        assert not update_entry_status(entry_id, "completed", expected_status="pending")

        # Should succeed: dispatching -> completed
        assert update_entry_status(entry_id, "completed", expected_status="dispatching")

    def test_count_active_for_trigger(self, isolated_db):
        """Count only dispatching entries for a specific trigger."""
        id_a = enqueue_execution("trig-abc", "webhook", "A", "{}")
        enqueue_execution("trig-abc", "webhook", "B", "{}")
        enqueue_execution("trig-def", "webhook", "C", "{}")

        assert count_active_for_trigger("trig-abc") == 0

        update_entry_status(id_a, "dispatching", expected_status="pending")
        assert count_active_for_trigger("trig-abc") == 1
        assert count_active_for_trigger("trig-def") == 0

    def test_get_queue_depth(self, isolated_db):
        """Queue depth counts only pending entries."""
        enqueue_execution("trig-abc", "webhook", "A", "{}")
        id_b = enqueue_execution("trig-abc", "webhook", "B", "{}")
        enqueue_execution("trig-def", "webhook", "C", "{}")

        assert get_queue_depth() == 3
        assert get_queue_depth("trig-abc") == 2
        assert get_queue_depth("trig-def") == 1

        # Dispatching reduces pending count
        update_entry_status(id_b, "dispatching", expected_status="pending")
        assert get_queue_depth("trig-abc") == 1

    def test_get_queue_summary(self, isolated_db):
        """Summary returns per-trigger pending/dispatching counts."""
        id_a = enqueue_execution("trig-abc", "webhook", "A", "{}")
        enqueue_execution("trig-abc", "webhook", "B", "{}")
        enqueue_execution("trig-def", "webhook", "C", "{}")

        update_entry_status(id_a, "dispatching", expected_status="pending")

        summary = get_queue_summary()
        summary_dict = {s["trigger_id"]: s for s in summary}

        assert summary_dict["trig-abc"]["pending"] == 1
        assert summary_dict["trig-abc"]["dispatching"] == 1
        assert summary_dict["trig-def"]["pending"] == 1
        assert summary_dict["trig-def"]["dispatching"] == 0

    def test_cancel_pending_entries(self, isolated_db):
        """Cancel pending entries by trigger or globally."""
        enqueue_execution("trig-abc", "webhook", "A", "{}")
        enqueue_execution("trig-abc", "webhook", "B", "{}")
        enqueue_execution("trig-def", "webhook", "C", "{}")

        cancelled = cancel_pending_entries("trig-abc")
        assert cancelled == 2
        assert get_queue_depth("trig-abc") == 0
        assert get_queue_depth("trig-def") == 1

    def test_reset_stale_dispatching(self, isolated_db):
        """Stale dispatching entries are reset to pending on recovery."""
        id_a = enqueue_execution("trig-abc", "webhook", "A", "{}")
        id_b = enqueue_execution("trig-abc", "webhook", "B", "{}")

        update_entry_status(id_a, "dispatching", expected_status="pending")
        update_entry_status(id_b, "dispatching", expected_status="pending")

        recovered = reset_stale_dispatching()
        assert recovered == 2

        entries = get_pending_entries()
        assert len(entries) == 2
        assert all(e["status"] == "pending" for e in entries)


# --- Service tests ---


class TestExecutionQueueService:
    """Test ExecutionQueueService enqueue, dispatch, and concurrency."""

    def test_enqueue_creates_entry(self, isolated_db):
        """Service enqueue creates a queue entry."""
        entry_id = ExecutionQueueService.enqueue("trig-abc", "webhook", "hello", {"key": "val"})
        assert entry_id.startswith("qe-")
        assert get_queue_depth("trig-abc") == 1

    def test_max_queue_depth_rejects(self, isolated_db):
        """Enqueue raises QueueFullError when per-trigger depth exceeded."""
        for i in range(MAX_QUEUE_DEPTH_PER_TRIGGER):
            ExecutionQueueService.enqueue("trig-abc", "webhook", f"msg-{i}")

        with pytest.raises(QueueFullError):
            ExecutionQueueService.enqueue("trig-abc", "webhook", "overflow")

        # Different trigger should still work
        entry_id = ExecutionQueueService.enqueue("trig-def", "webhook", "ok")
        assert entry_id.startswith("qe-")

    def test_concurrency_cap_enforcement(self, isolated_db):
        """Dispatcher respects per-trigger concurrency cap."""
        ExecutionQueueService.set_concurrency_cap("trig-abc", 1)

        # Enqueue 3 entries
        ids = []
        for i in range(3):
            ids.append(ExecutionQueueService.enqueue("trig-abc", "webhook", f"msg-{i}"))

        dispatched = []
        dispatch_event = threading.Event()

        def mock_execute_with_fallback(trigger, message_text, event, trigger_type):
            dispatched.append(message_text)
            dispatch_event.set()
            time.sleep(0.5)  # Hold the slot

        with (
            patch(
                "app.database.get_trigger",
                return_value={"id": "trig-abc", "backend_type": "claude"},
            ),
            patch(
                "app.services.orchestration_service.OrchestrationService.execute_with_fallback",
                side_effect=mock_execute_with_fallback,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService.can_execute",
                return_value=True,
            ),
        ):
            ExecutionQueueService.start_dispatcher()

            # Wait for first dispatch
            dispatch_event.wait(timeout=5.0)
            time.sleep(0.1)

            # Only 1 should be dispatching (cap=1)
            active = count_active_for_trigger("trig-abc")
            assert active <= 1

        ExecutionQueueService.stop_dispatcher()

    def test_dispatcher_picks_up_pending(self, isolated_db):
        """Dispatcher picks up pending entries and dispatches them."""
        ExecutionQueueService.enqueue("trig-abc", "webhook", "test-msg", {"data": "value"})

        dispatched = []
        done_event = threading.Event()

        def mock_execute(trigger, message_text, event, trigger_type):
            dispatched.append(message_text)
            done_event.set()

        with (
            patch(
                "app.database.get_trigger",
                return_value={"id": "trig-abc", "backend_type": "claude"},
            ),
            patch(
                "app.services.orchestration_service.OrchestrationService.execute_with_fallback",
                side_effect=mock_execute,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService.can_execute",
                return_value=True,
            ),
        ):
            ExecutionQueueService.start_dispatcher()
            done_event.wait(timeout=5.0)
            ExecutionQueueService.stop_dispatcher()

        assert "test-msg" in dispatched

    def test_circuit_breaker_open_keeps_pending(self, isolated_db):
        """Entry stays pending when circuit breaker is OPEN."""
        ExecutionQueueService.enqueue("trig-abc", "webhook", "blocked-msg")

        with (
            patch(
                "app.database.get_trigger",
                return_value={"id": "trig-abc", "backend_type": "claude"},
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService.can_execute",
                return_value=False,
            ),
        ):
            ExecutionQueueService.start_dispatcher()
            time.sleep(2.5)  # Let dispatcher poll a couple times
            ExecutionQueueService.stop_dispatcher()

        # Entry should still be pending
        entries = get_pending_entries()
        assert len(entries) == 1
        assert entries[0]["status"] == "pending"

    def test_fifo_dispatch_order(self, isolated_db):
        """Entries are dispatched in FIFO order."""
        ExecutionQueueService.enqueue("trig-abc", "webhook", "first")
        ExecutionQueueService.enqueue("trig-abc", "webhook", "second")
        ExecutionQueueService.enqueue("trig-abc", "webhook", "third")

        dispatched = []
        all_done = threading.Event()

        def mock_execute(trigger, message_text, event, trigger_type):
            dispatched.append(message_text)
            if len(dispatched) >= 3:
                all_done.set()

        with (
            patch(
                "app.database.get_trigger",
                return_value={"id": "trig-abc", "backend_type": "claude"},
            ),
            patch(
                "app.services.orchestration_service.OrchestrationService.execute_with_fallback",
                side_effect=mock_execute,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService.can_execute",
                return_value=True,
            ),
        ):
            # Set cap to 3 so all can dispatch at once (but FIFO ordering is still checked)
            ExecutionQueueService.set_concurrency_cap("trig-abc", 3)
            ExecutionQueueService.start_dispatcher()
            all_done.wait(timeout=10.0)
            ExecutionQueueService.stop_dispatcher()

        assert dispatched == ["first", "second", "third"]

    def test_queue_survives_restart(self, isolated_db):
        """Stale dispatching entries recover to pending on restart."""
        id_a = ExecutionQueueService.enqueue("trig-abc", "webhook", "stale-1")
        id_b = ExecutionQueueService.enqueue("trig-abc", "webhook", "stale-2")

        # Simulate crash: mark as dispatching without completing
        update_entry_status(id_a, "dispatching", expected_status="pending")
        update_entry_status(id_b, "dispatching", expected_status="pending")

        assert count_active_for_trigger("trig-abc") == 2
        assert get_queue_depth("trig-abc") == 0

        # Directly call stale recovery (what start_dispatcher does internally)
        recovered = reset_stale_dispatching()
        assert recovered == 2

        # Entries should be back to pending
        assert get_queue_depth("trig-abc") == 2

    def test_concurrency_cap_default(self, isolated_db):
        """Default concurrency cap is 1."""
        assert ExecutionQueueService.get_concurrency_cap("any-trigger") == 1

    def test_set_concurrency_cap(self, isolated_db):
        """Setting a cap persists in memory."""
        ExecutionQueueService.set_concurrency_cap("trig-abc", 5)
        assert ExecutionQueueService.get_concurrency_cap("trig-abc") == 5
        # Minimum cap is 1
        ExecutionQueueService.set_concurrency_cap("trig-abc", 0)
        assert ExecutionQueueService.get_concurrency_cap("trig-abc") == 1


# --- API endpoint tests ---


class TestQueueAPIEndpoints:
    """Test admin queue API endpoints."""

    @pytest.fixture
    def client(self, isolated_db):
        """Create Flask test client."""
        from app import create_app

        app = create_app({"TESTING": True})
        with app.test_client() as client:
            yield client

    def test_get_queue_status(self, client, isolated_db):
        """GET /admin/executions/queue returns queue summary."""
        enqueue_execution("trig-abc", "webhook", "A", "{}")
        enqueue_execution("trig-def", "github", "B", "{}")

        resp = client.get("/admin/executions/queue")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "queue" in data
        assert data["total_pending"] == 2

    def test_get_queue_for_trigger(self, client, isolated_db):
        """GET /admin/executions/queue/<trigger_id> returns trigger-specific depth."""
        enqueue_execution("trig-abc", "webhook", "A", "{}")
        enqueue_execution("trig-abc", "webhook", "B", "{}")

        resp = client.get("/admin/executions/queue/trig-abc")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trigger_id"] == "trig-abc"
        assert data["pending"] == 2

    def test_cancel_queue_for_trigger(self, client, isolated_db):
        """DELETE /admin/executions/queue/<trigger_id> cancels pending entries."""
        enqueue_execution("trig-abc", "webhook", "A", "{}")
        enqueue_execution("trig-abc", "webhook", "B", "{}")

        resp = client.delete("/admin/executions/queue/trig-abc")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cancelled"] == 2

        assert get_queue_depth("trig-abc") == 0

    def test_get_pending_retries(self, client, isolated_db):
        """GET /admin/executions/retries returns pending retry entries."""
        resp = client.get("/admin/executions/retries")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "retries" in data
        assert "total" in data
        assert data["total"] == 0

    def test_get_pending_retries_with_data(self, client, isolated_db):
        """GET /admin/executions/retries returns populated retry entries."""
        from app.db.monitoring import upsert_pending_retry

        upsert_pending_retry(
            trigger_id="trig-abc",
            trigger_json='{"id": "trig-abc"}',
            message_text="test",
            event_json="{}",
            trigger_type="webhook",
            cooldown_seconds=60,
            retry_at="2026-03-05T12:00:00",
        )

        resp = client.get("/admin/executions/retries")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["retries"][0]["trigger_id"] == "trig-abc"
        assert data["retries"][0]["cooldown_seconds"] == 60
