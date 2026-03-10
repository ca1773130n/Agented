"""Tests for concurrent/threaded operations across execution services."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.execution_service import ExecutionService, ExecutionState
from app.services.process_manager import ProcessManager, ProcessInfo
from app.services.team_execution_service import TeamExecutionService
from app.services.execution_queue_service import ExecutionQueueService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_execution_service_state():
    """Reset class-level mutable state between tests."""
    ExecutionService._rate_limit_detected.clear()
    ExecutionService._transient_failure_detected.clear()
    ExecutionService._pending_retries.clear()
    for timer in ExecutionService._retry_timers.values():
        timer.cancel()
    ExecutionService._retry_timers.clear()
    ExecutionService._retry_counts.clear()
    yield
    ExecutionService._rate_limit_detected.clear()
    ExecutionService._transient_failure_detected.clear()
    ExecutionService._pending_retries.clear()
    for timer in ExecutionService._retry_timers.values():
        timer.cancel()
    ExecutionService._retry_timers.clear()
    ExecutionService._retry_counts.clear()


@pytest.fixture(autouse=True)
def reset_process_manager():
    """Reset ProcessManager state between tests."""
    ProcessManager._processes.clear()
    ProcessManager._cancelled.clear()
    yield
    ProcessManager._processes.clear()
    ProcessManager._cancelled.clear()


@pytest.fixture(autouse=True)
def reset_team_execution_service():
    """Reset TeamExecutionService state between tests.

    Defensively re-creates _executions if another test removed or replaced it.
    """
    # Re-import to ensure we have the real class (not a mock)
    from app.services.team_execution_service import TeamExecutionService as TES

    if not hasattr(TES, "_executions") or not isinstance(getattr(TES, "_executions", None), dict):
        TES._executions = {}
    else:
        TES._executions.clear()
    yield
    if hasattr(TES, "_executions") and isinstance(TES._executions, dict):
        TES._executions.clear()


@pytest.fixture(autouse=True)
def reset_queue_service():
    """Reset ExecutionQueueService state between tests."""
    ExecutionQueueService.stop_dispatcher()
    ExecutionQueueService._concurrency_caps.clear()
    yield
    ExecutionQueueService.stop_dispatcher()
    ExecutionQueueService._concurrency_caps.clear()


def _make_trigger(**overrides):
    """Build a minimal trigger dict with sensible defaults."""
    trigger = {
        "id": "trg-test01",
        "name": "Test Trigger",
        "trigger_source": "webhook",
        "backend_type": "claude",
        "prompt_template": "Analyze {message} at {paths}",
        "enabled": 1,
    }
    trigger.update(overrides)
    return trigger


# ---------------------------------------------------------------------------
# Thread-safe access to ExecutionService class-level state dicts
# ---------------------------------------------------------------------------


class TestExecutionServiceThreadSafety:
    def test_concurrent_rate_limit_writes(self, isolated_db):
        """Multiple threads writing to _rate_limit_detected concurrently should not corrupt data."""
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        errors = []

        def writer(thread_id):
            try:
                barrier.wait(timeout=5)
                exec_id = f"exec-{thread_id}"
                with ExecutionService._rate_limit_lock:
                    ExecutionService._rate_limit_detected[exec_id] = thread_id * 10
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        assert len(ExecutionService._rate_limit_detected) == num_threads
        for i in range(num_threads):
            assert ExecutionService._rate_limit_detected[f"exec-{i}"] == i * 10

    def test_concurrent_was_rate_limited_pops(self, isolated_db):
        """Concurrent was_rate_limited calls should each pop exactly once (no double-pop)."""
        # Pre-populate
        for i in range(50):
            ExecutionService._rate_limit_detected[f"exec-{i}"] = i

        results = {}
        lock = threading.Lock()
        barrier = threading.Barrier(50)

        def reader(thread_id):
            barrier.wait(timeout=5)
            val = ExecutionService.was_rate_limited(f"exec-{thread_id}")
            with lock:
                results[thread_id] = val

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Each thread should have gotten its value exactly once
        for i in range(50):
            assert results[i] == i

        # Dict should be empty after all pops
        assert len(ExecutionService._rate_limit_detected) == 0

    def test_concurrent_transient_failure_writes(self, isolated_db):
        """Concurrent writes to _transient_failure_detected should be thread-safe."""
        num_threads = 20
        barrier = threading.Barrier(num_threads)

        def writer(thread_id):
            barrier.wait(timeout=5)
            with ExecutionService._rate_limit_lock:
                ExecutionService._transient_failure_detected[f"exec-{thread_id}"] = (
                    f"error-{thread_id}"
                )

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(ExecutionService._transient_failure_detected) == num_threads


# ---------------------------------------------------------------------------
# ProcessManager thread safety
# ---------------------------------------------------------------------------


class TestProcessManagerThreadSafety:
    def test_concurrent_register_and_cleanup(self, isolated_db):
        """Concurrent register and cleanup calls should not corrupt _processes."""
        num_ops = 30
        barrier = threading.Barrier(num_ops)

        def register_and_cleanup(i):
            barrier.wait(timeout=5)
            exec_id = f"exec-pm-{i}"
            mock_proc = MagicMock()
            mock_proc.pid = 10000 + i
            with patch("os.getpgid", return_value=10000 + i):
                ProcessManager.register(exec_id, mock_proc, f"trg-{i}")
            # Immediately cleanup
            ProcessManager.cleanup(exec_id)

        threads = [threading.Thread(target=register_and_cleanup, args=(i,)) for i in range(num_ops)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # All should have been cleaned up
        assert ProcessManager.get_active_count() == 0

    def test_concurrent_cancel_same_execution(self, isolated_db):
        """Multiple threads cancelling the same execution should not raise."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        with patch("os.getpgid", return_value=54321):
            ProcessManager.register("exec-shared", mock_proc, "trg-1")

        barrier = threading.Barrier(10)
        results = []
        lock = threading.Lock()

        def canceller(i):
            barrier.wait(timeout=5)
            with patch("os.killpg"):
                result = ProcessManager.cancel("exec-shared")
            with lock:
                results.append(result)

        threads = [threading.Thread(target=canceller, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # At least one should have succeeded, all should have returned without error
        assert len(results) == 10
        assert any(r is True for r in results)

    def test_concurrent_is_cancelled_checks(self, isolated_db):
        """is_cancelled should be safe to call from multiple threads."""
        ProcessManager._cancelled.add("exec-c1")
        barrier = threading.Barrier(20)
        results = []
        lock = threading.Lock()

        def checker(i):
            barrier.wait(timeout=5)
            r = ProcessManager.is_cancelled("exec-c1")
            with lock:
                results.append(r)

        threads = [threading.Thread(target=checker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert all(r is True for r in results)


# ---------------------------------------------------------------------------
# TeamExecutionService parallel execution with real threads
# ---------------------------------------------------------------------------


class TestTeamParallelExecution:
    def test_parallel_execution_collects_all_ids(self, isolated_db):
        """_execute_parallel should run agents in threads and collect all execution IDs."""
        team = {"id": "team-01", "name": "Test Team", "members": []}
        config = {"agents": ["agent-1", "agent-2", "agent-3"]}

        call_count = {"n": 0}
        call_lock = threading.Lock()

        def mock_run_agent(team, agent_id, message, event, trigger_type, wd=None):
            with call_lock:
                call_count["n"] += 1
                idx = call_count["n"]
            # Simulate some work
            time.sleep(0.01)
            return f"exec-{agent_id}", f"output-{agent_id}"

        with patch.object(TeamExecutionService, "_run_agent_and_get_output", side_effect=mock_run_agent):
            result = TeamExecutionService._execute_parallel(
                team, config, "test message", None, "manual"
            )

        assert len(result) == 3
        assert all(eid.startswith("exec-") for eid in result)

    def test_parallel_execution_thread_safety_of_execution_ids(self, isolated_db):
        """Parallel agent results should not have duplicates or missing entries."""
        team = {"id": "team-02", "name": "Test Team", "members": []}
        num_agents = 20
        config = {"agents": [f"agent-{i}" for i in range(num_agents)]}

        def mock_run_agent(team, agent_id, message, event, trigger_type, wd=None):
            time.sleep(0.005)  # Simulate concurrent work
            return f"exec-{agent_id}", ""

        with patch.object(TeamExecutionService, "_run_agent_and_get_output", side_effect=mock_run_agent):
            result = TeamExecutionService._execute_parallel(
                team, config, "test", None, "manual"
            )

        assert len(result) == num_agents
        assert len(set(result)) == num_agents  # No duplicates

    def test_parallel_execution_handles_agent_failure(self, isolated_db):
        """If one agent returns None execution_id, others should still succeed."""
        team = {"id": "team-03", "name": "Test Team", "members": []}
        config = {"agents": ["agent-ok", "agent-fail", "agent-ok2"]}

        def mock_run_agent(team, agent_id, message, event, trigger_type, wd=None):
            if agent_id == "agent-fail":
                return None, ""  # Simulate failure
            return f"exec-{agent_id}", "output"

        with patch.object(TeamExecutionService, "_run_agent_and_get_output", side_effect=mock_run_agent):
            result = TeamExecutionService._execute_parallel(
                team, config, "test", None, "manual"
            )

        assert len(result) == 2
        assert "exec-agent-ok" in result
        assert "exec-agent-ok2" in result


# ---------------------------------------------------------------------------
# TeamExecutionService coordinator parallel workers with real threads
# ---------------------------------------------------------------------------


class TestTeamCoordinatorParallel:
    def test_coordinator_then_parallel_workers(self, isolated_db):
        """Coordinator topology should run coordinator first, then workers in parallel."""
        team = {"id": "team-coord", "name": "Coord Team", "members": []}
        config = {"coordinator": "agent-coord", "workers": ["agent-w1", "agent-w2"]}

        call_order = []
        call_lock = threading.Lock()

        def mock_run_agent(team, agent_id, message, event, trigger_type, wd=None):
            with call_lock:
                call_order.append(agent_id)
            if agent_id == "agent-coord":
                time.sleep(0.01)
                return "exec-coord", "coordinator instructions"
            else:
                time.sleep(0.01)
                return f"exec-{agent_id}", f"output-{agent_id}"

        with patch.object(TeamExecutionService, "_run_agent_and_get_output", side_effect=mock_run_agent):
            result = TeamExecutionService._execute_coordinator(
                team, config, "initial", None, "manual"
            )

        # Coordinator should be first in call order
        assert call_order[0] == "agent-coord"
        assert len(result) == 3  # coordinator + 2 workers


# ---------------------------------------------------------------------------
# TeamExecutionService concurrent execute_team calls
# ---------------------------------------------------------------------------


class TestTeamConcurrentExecutions:
    def test_concurrent_execute_team_isolation(self, isolated_db):
        """Multiple concurrent execute_team calls should each get unique tracking IDs."""
        barrier = threading.Barrier(5)
        results = []
        lock = threading.Lock()

        # Patches must be started before threads so they apply globally
        p_strategy = patch.object(TeamExecutionService, "_run_strategy")
        p_detail = patch.object(
            TeamExecutionService,
            "execute_team",
            wraps=TeamExecutionService.execute_team,
        )

        # We need get_team_detail to return valid data for any team_id
        def fake_get_team_detail(team_id):
            return {
                "id": team_id,
                "name": f"Team {team_id}",
                "enabled": 1,
                "topology": "parallel",
                "topology_config": '{"agents": []}',
                "members": [],
            }

        p_detail_db = patch(
            "app.database.get_team_detail",
            side_effect=fake_get_team_detail,
        )
        mock_strategy = p_strategy.start()
        p_detail_db.start()

        try:
            def run_team(i):
                barrier.wait(timeout=5)
                exec_id = TeamExecutionService.execute_team(f"team-{i}", f"msg-{i}")
                with lock:
                    results.append(exec_id)

            threads = [threading.Thread(target=run_team, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
        finally:
            p_strategy.stop()
            p_detail_db.stop()

        # All should have unique IDs
        assert len(results) == 5
        assert len(set(results)) == 5

    def test_concurrent_get_execution_status(self, isolated_db):
        """Concurrent reads of execution status should not corrupt state."""
        # Pre-populate
        with TeamExecutionService._lock:
            TeamExecutionService._executions["te-1"] = {
                "team_id": "t1",
                "status": "running",
                "execution_ids": [],
            }

        barrier = threading.Barrier(20)
        results = []
        lock = threading.Lock()

        def reader(i):
            barrier.wait(timeout=5)
            status = TeamExecutionService.get_execution_status("te-1")
            with lock:
                results.append(status)

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert all(r is not None for r in results)
        assert all(r["status"] == "running" for r in results)


# ---------------------------------------------------------------------------
# ExecutionQueueService concurrent enqueue/dequeue
# ---------------------------------------------------------------------------


class TestQueueServiceConcurrency:
    def test_concurrent_enqueue(self, isolated_db):
        """Multiple threads enqueuing simultaneously should not lose entries."""
        num_threads = 15
        barrier = threading.Barrier(num_threads)
        entry_ids = []
        lock = threading.Lock()
        errors = []

        def enqueuer(i):
            try:
                barrier.wait(timeout=5)
                entry_id = ExecutionQueueService.enqueue(
                    trigger_id=f"trg-q-{i}",
                    trigger_type="webhook",
                    message_text=f"message-{i}",
                )
                with lock:
                    entry_ids.append(entry_id)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=enqueuer, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors during enqueue: {errors}"
        assert len(entry_ids) == num_threads
        assert len(set(entry_ids)) == num_threads  # All unique

    def test_concurrent_set_concurrency_cap(self, isolated_db):
        """Setting concurrency caps from multiple threads should not corrupt state."""
        num_threads = 20
        barrier = threading.Barrier(num_threads)

        def setter(i):
            barrier.wait(timeout=5)
            ExecutionQueueService.set_concurrency_cap(f"trg-cap-{i}", i + 1)

        threads = [threading.Thread(target=setter, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        for i in range(num_threads):
            assert ExecutionQueueService.get_concurrency_cap(f"trg-cap-{i}") == max(1, i + 1)


# ---------------------------------------------------------------------------
# Real threading with _stream_pipe
# ---------------------------------------------------------------------------


class TestStreamPipeRealThreads:
    def test_concurrent_stream_pipes(self, isolated_db):
        """Multiple _stream_pipe threads reading different pipes concurrently."""
        import io

        num_pipes = 5
        threads = []
        collected = {}
        collect_lock = threading.Lock()

        with patch("app.services.execution_runner.ExecutionLogService") as mock_log:
            def capture_log(exec_id, stream, content):
                with collect_lock:
                    collected.setdefault(exec_id, []).append(content)

            mock_log.append_log.side_effect = capture_log

            for i in range(num_pipes):
                pipe = io.StringIO(f"line-{i}-a\nline-{i}-b\n")
                t = threading.Thread(
                    target=ExecutionService._stream_pipe,
                    args=(f"exec-{i}", "stdout", pipe),
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=10)

        # Each pipe should have produced exactly 2 lines
        for i in range(num_pipes):
            assert len(collected[f"exec-{i}"]) == 2
            assert collected[f"exec-{i}"][0] == f"line-{i}-a"
            assert collected[f"exec-{i}"][1] == f"line-{i}-b"


# ---------------------------------------------------------------------------
# Concurrent schedule_retry calls
# ---------------------------------------------------------------------------


class TestConcurrentRetryScheduling:
    def test_concurrent_schedule_retry_different_triggers(self, isolated_db):
        """Concurrent schedule_retry for different triggers should not interfere."""
        num_triggers = 10
        barrier = threading.Barrier(num_triggers)
        errors = []

        def schedule(i):
            try:
                barrier.wait(timeout=5)
                trigger = _make_trigger(id=f"trg-retry-{i}")
                with (
                    patch("app.services.audit_log_service.AuditLogService"),
                    patch("app.services.execution_retry.upsert_pending_retry"),
                ):
                    ExecutionService.schedule_retry(
                        trigger=trigger,
                        message_text=f"msg-{i}",
                        event=None,
                        trigger_type="webhook",
                        cooldown_seconds=60,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=schedule, args=(i,)) for i in range(num_triggers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        assert len(ExecutionService._retry_timers) == num_triggers
        assert len(ExecutionService._pending_retries) == num_triggers

        # Cleanup timers
        for timer in ExecutionService._retry_timers.values():
            timer.cancel()
