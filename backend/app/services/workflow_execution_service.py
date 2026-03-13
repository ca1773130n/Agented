"""Workflow execution service — DAG execution engine with topological sort, node dispatch,
error handling, retry, and timeout."""

import graphlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..models.workflow import NodeErrorMode, WorkflowMessage

# Re-export evaluate_condition so existing imports continue to work:
#   from app.services.workflow_execution_service import evaluate_condition
from .workflow_expression_evaluator import evaluate_condition  # noqa: F401
from .workflow_node_executor import NodeExecutor

logger = logging.getLogger(__name__)


class WorkflowExecutionService:
    """DAG-based workflow execution engine.

    Executes workflow graphs by topologically sorting nodes, dispatching each
    to the appropriate handler, routing I/O via WorkflowMessage envelopes,
    and providing per-node error handling, retry with exponential backoff,
    and workflow-level timeout enforcement.

    Follows the TeamExecutionService pattern: in-memory dict under threading.Lock,
    background daemon thread, strategy dispatch map.
    """

    # In-memory tracking of workflow executions: {execution_id: status_dict}
    _executions: Dict[str, dict] = {}
    _lock = threading.Lock()

    # In-memory approval events: {(execution_id, node_id): threading.Event}
    _approval_events: Dict[tuple, threading.Event] = {}
    _approval_lock = threading.Lock()

    # Rejection flags: {(execution_id, node_id): True}
    _rejection_flags: Dict[tuple, bool] = {}

    DEFAULT_TIMEOUT_SECONDS = 1800  # 30 minutes

    # Node type dispatcher map (kept for backward compatibility with tests that
    # reference NODE_DISPATCHERS or patch individual _execute_* methods)
    NODE_DISPATCHERS = {
        "trigger": "_execute_trigger_node",
        "skill": "_execute_skill_node",
        "command": "_execute_command_node",
        "agent": "_execute_agent_node",
        "script": "_execute_script_node",
        "conditional": "_execute_conditional_node",
        "transform": "_execute_transform_node",
        "approval_gate": "_execute_approval_gate_node",
    }

    @staticmethod
    def _sort_nodes(nodes: dict, edges_list: list) -> list:
        """Build topological sort order from nodes dict and edges list.

        Returns a list of node_ids in topological order.
        Raises graphlib.CycleError if the graph contains a cycle.
        """
        predecessors: Dict[str, set] = {nid: set() for nid in nodes}
        for edge in edges_list:
            predecessors[edge["target"]].add(edge["source"])
        return list(graphlib.TopologicalSorter(predecessors).static_order())

    @staticmethod
    def _collect_results(topo_order: list, node_outputs: dict) -> Optional[str]:
        """Get the last non-empty node output as JSON string for the workflow output.

        Walks topo_order in reverse to find the last node that produced output.
        Returns a JSON string or None if no node produced output.
        """
        for nid in reversed(topo_order):
            if nid in node_outputs:
                return node_outputs[nid].model_dump_json()
        return None

    @staticmethod
    def _validate_graph(graph_parsed: dict) -> None:
        """Validate workflow graph structure before execution.

        Raises ValueError with a descriptive message for:
        - Edges missing source or target fields
        - Edges referencing node IDs not defined in the graph
        - Circular dependencies (cycle detection via topological sort)
        """
        nodes_list = graph_parsed.get("nodes", [])
        edges_list = graph_parsed.get("edges", [])

        node_ids = set()
        for node in nodes_list:
            if "id" not in node:
                raise ValueError("Graph contains a node without an 'id' field")
            node_ids.add(node["id"])

        predecessors: Dict[str, set] = {nid: set() for nid in node_ids}
        for edge in edges_list:
            if "source" not in edge or "target" not in edge:
                raise ValueError(f"Edge missing 'source' or 'target': {edge}")
            src, tgt = edge["source"], edge["target"]
            if src not in node_ids:
                raise ValueError(f"Edge source references undefined node: '{src}'")
            if tgt not in node_ids:
                raise ValueError(f"Edge target references undefined node: '{tgt}'")
            predecessors[tgt].add(src)

        # Detect cycles via topological sort
        try:
            list(graphlib.TopologicalSorter(predecessors).static_order())
        except graphlib.CycleError as e:
            raise ValueError(f"Graph contains a circular dependency: {e}") from e

    @classmethod
    def execute_workflow(
        cls,
        workflow_id: str,
        input_json: Optional[str] = None,
        trigger_type: str = "manual",
        timeout_seconds: Optional[int] = None,
    ) -> str:
        """Start executing a workflow in a background thread.

        Loads the workflow and its latest version, creates an execution record,
        and dispatches the DAG execution to a daemon thread.

        Args:
            workflow_id: ID of the workflow to execute.
            input_json: Optional JSON string of initial input data.
            trigger_type: How the workflow was triggered (manual, webhook, etc).

        Returns:
            execution_id: The tracking ID for this execution (wfx-*).

        Raises:
            ValueError: If workflow not found, disabled, or has no versions.
        """
        from ..db.workflows import (
            add_workflow_execution,
            get_latest_workflow_version,
            get_workflow,
        )

        # Load workflow
        workflow = get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")
        if not workflow.get("enabled", 1):
            raise ValueError(f"Workflow is disabled: {workflow_id}")

        # Load latest version
        latest = get_latest_workflow_version(workflow_id)
        if not latest:
            raise ValueError(f"Workflow has no versions: {workflow_id}")

        # Parse graph
        graph_json_str = latest["graph_json"]
        try:
            graph_parsed = json.loads(graph_json_str)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid graph JSON: {e}")

        # Validate graph structure before committing to execution
        cls._validate_graph(graph_parsed)

        # Extract settings — per-run override takes precedence over graph settings
        settings = graph_parsed.get("settings") or {}
        graph_timeout = settings.get("timeout_seconds", cls.DEFAULT_TIMEOUT_SECONDS)
        effective_timeout = timeout_seconds if timeout_seconds is not None else graph_timeout

        # Create DB execution record (status=running)
        execution_id = add_workflow_execution(
            workflow_id=workflow_id,
            version=latest["version"],
            input_json=input_json,
            status="running",
        )
        if not execution_id:
            raise ValueError("Failed to create workflow execution record")

        # Register in-memory tracking
        with cls._lock:
            cls._executions[execution_id] = {
                "workflow_id": workflow_id,
                "status": "running",
                "trigger_type": trigger_type,
                "node_states": {},
                "_cancelled": False,
            }

        # Start background daemon thread
        thread = threading.Thread(
            target=cls._run_workflow,
            args=(
                execution_id,
                workflow_id,
                graph_parsed,
                input_json,
                trigger_type,
                effective_timeout,
            ),
            daemon=True,
        )
        thread.start()

        logger.info(
            f"Workflow execution started: {execution_id} "
            f"(workflow={workflow_id}, trigger={trigger_type}, timeout={effective_timeout}s)"
        )
        return execution_id

    @classmethod
    def get_execution_status(cls, execution_id: str) -> Optional[dict]:
        """Get in-memory execution status, falling back to DB if not tracked."""
        with cls._lock:
            mem = cls._executions.get(execution_id)
            if mem:
                return {
                    "execution_id": execution_id,
                    "workflow_id": mem["workflow_id"],
                    "status": mem["status"],
                    "node_states": dict(mem.get("node_states", {})),
                    "error": mem.get("error"),
                }

        # Fall back to DB
        from ..db.workflows import get_workflow_execution

        db_exec = get_workflow_execution(execution_id)
        if db_exec:
            return {
                "execution_id": execution_id,
                "workflow_id": db_exec["workflow_id"],
                "status": db_exec["status"],
                "error": db_exec.get("error"),
            }
        return None

    @classmethod
    def cancel_execution(cls, execution_id: str) -> bool:
        """Cancel a running execution by setting the _cancelled flag."""
        with cls._lock:
            entry = cls._executions.get(execution_id)
            if entry and entry["status"] == "running":
                entry["_cancelled"] = True
                return True
        return False

    @classmethod
    def _is_cancelled(cls, execution_id: str) -> bool:
        """Check if an execution has been cancelled."""
        with cls._lock:
            entry = cls._executions.get(execution_id)
            return bool(entry and entry.get("_cancelled"))

    @classmethod
    def _update_status(cls, execution_id: str, status: str, error: str = None) -> None:
        """Update in-memory execution status."""
        with cls._lock:
            entry = cls._executions.get(execution_id)
            if entry:
                entry["status"] = status
                if error:
                    entry["error"] = error

    @classmethod
    def _update_node_state(cls, execution_id: str, node_id: str, status: str) -> None:
        """Update in-memory node state."""
        with cls._lock:
            entry = cls._executions.get(execution_id)
            if entry:
                entry.setdefault("node_states", {})[node_id] = status

    @classmethod
    def cleanup_stale_executions(cls) -> None:
        """Mark any DB-persisted 'running' or 'pending_approval' executions as failed.

        Called once at server startup to recover from unclean shutdowns where
        in-memory execution state was lost but DB records were left as 'running'
        or 'pending_approval'. Also cleans up stale approval states whose
        in-memory Events are lost (per research Pitfall 2).
        """
        from ..db.workflows import get_running_workflow_executions, update_workflow_execution

        stale = get_running_workflow_executions()
        if not stale:
            pass
        else:
            now = datetime.now(timezone.utc).isoformat()
            for execution in stale:
                execution_id = execution["id"]
                update_workflow_execution(
                    execution_id,
                    status="failed",
                    error="Server restarted while execution was running",
                    ended_at=now,
                )
                logger.warning(
                    "Marked stale workflow execution as failed on startup: %s", execution_id
                )

        # Clean up stale pending approval states (in-memory Events are lost on restart)
        try:
            from ..db.workflows import cleanup_stale_approval_states

            count = cleanup_stale_approval_states()
            if count > 0:
                logger.warning(
                    "Marked %d stale pending approval states as timed_out on startup", count
                )
        except Exception as e:
            logger.error("Failed to cleanup stale approval states: %s", e, exc_info=True)

    @classmethod
    def _cleanup_execution(cls, execution_id: str) -> None:
        """Remove execution from in-memory tracking (called after TTL)."""
        with cls._lock:
            cls._executions.pop(execution_id, None)

    # =========================================================================
    # Core DAG Execution
    # =========================================================================

    @classmethod
    def _run_workflow(
        cls,
        execution_id: str,
        workflow_id: str,
        graph_parsed: dict,
        input_json: Optional[str],
        trigger_type: str,
        timeout_seconds: int,
    ) -> None:
        """Execute the workflow DAG in topological order.

        This method runs in a background daemon thread. It:
        1. Parses the graph into nodes and edges
        2. Builds a topological sort order
        3. Executes each node in order, routing I/O via WorkflowMessage
        4. Handles error modes, retry, and timeout
        5. Updates DB records for each node and the overall execution
        """
        from ..db.workflows import (
            add_workflow_node_execution,
            get_workflow_node_executions,
            update_workflow_execution,
            update_workflow_node_execution,
        )

        nodes_list = graph_parsed.get("nodes", [])
        edges_list = graph_parsed.get("edges", [])

        # Build nodes dict keyed by node_id
        nodes = {}
        for node in nodes_list:
            nodes[node["id"]] = node

        # Build successor map for skip propagation
        successors: Dict[str, set] = {nid: set() for nid in nodes}
        for edge in edges_list:
            successors[edge["source"]].add(edge["target"])

        # Topological sort
        try:
            topo_order = cls._sort_nodes(nodes, edges_list)
        except graphlib.CycleError as e:
            error_msg = f"Graph cycle detected: {e}"
            logger.error(f"Workflow {execution_id}: {error_msg}", exc_info=True)
            cls._update_status(execution_id, "failed", error=error_msg)
            now = datetime.now(timezone.utc).isoformat()
            update_workflow_execution(execution_id, status="failed", error=error_msg, ended_at=now)
            cls._schedule_cleanup(execution_id)
            return

        # Build predecessor map (still needed for input routing per node)
        predecessors: Dict[str, set] = {nid: set() for nid in nodes}
        for edge in edges_list:
            predecessors[edge["target"]].add(edge["source"])

        # Initialize node outputs and tracking
        node_outputs: Dict[str, WorkflowMessage] = {}
        skipped_nodes: set = set()
        workflow_failed = False
        workflow_error = None
        start_time = time.time()

        # Parse initial input into WorkflowMessage
        initial_input = WorkflowMessage()
        if input_json:
            try:
                input_data = json.loads(input_json)
                if isinstance(input_data, dict):
                    initial_input = WorkflowMessage(data=input_data)
                elif isinstance(input_data, str):
                    initial_input = WorkflowMessage(text=input_data)
            except (json.JSONDecodeError, TypeError):
                initial_input = WorkflowMessage(text=input_json)

        # Execute each node in topological order
        for node_id in topo_order:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                logger.warning(
                    f"Workflow {execution_id}: timeout after {elapsed:.1f}s "
                    f"(limit={timeout_seconds}s)"
                )
                # Mark remaining nodes as skipped
                cls._update_node_state(execution_id, node_id, "skipped")
                workflow_failed = True
                workflow_error = f"Workflow timed out after {timeout_seconds} seconds"
                break

            # Check cancelled
            if cls._is_cancelled(execution_id):
                logger.info(f"Workflow {execution_id}: cancelled")
                cls._update_status(execution_id, "cancelled")
                now = datetime.now(timezone.utc).isoformat()
                update_workflow_execution(
                    execution_id, status="cancelled", error="Cancelled by user", ended_at=now
                )
                cls._schedule_cleanup(execution_id)
                return

            # Skip if any predecessor was skipped (due to error_mode=stop or continue)
            if node_id in skipped_nodes:
                cls._update_node_state(execution_id, node_id, "skipped")
                now = datetime.now(timezone.utc).isoformat()
                row_id = add_workflow_node_execution(
                    execution_id=execution_id,
                    node_id=node_id,
                    node_type=nodes[node_id].get("type", "unknown"),
                    input_json=None,
                )
                if row_id:
                    update_workflow_node_execution(
                        row_id, status="skipped", started_at=now, ended_at=now
                    )
                continue

            node = nodes[node_id]
            node_type = node.get("type", "unknown")
            node_config = node.get("config", {})
            error_mode = node.get("error_mode", NodeErrorMode.STOP)
            retry_max = node.get("retry_max", 0)
            retry_backoff = node.get("retry_backoff_seconds", 1)
            backoff_strategy = node.get("backoff_strategy", "exponential")

            # Gather input from predecessor nodes
            preds = predecessors.get(node_id, set())
            if not preds:
                # Root node: use initial input
                input_msg = initial_input
            elif len(preds) == 1:
                pred_id = next(iter(preds))
                input_msg = node_outputs.get(pred_id, WorkflowMessage())
            else:
                # Multiple predecessors: merge their outputs
                input_msg = cls._merge_messages(
                    [node_outputs.get(pid, WorkflowMessage()) for pid in preds]
                )

            # Create node execution DB record
            input_json_str = input_msg.model_dump_json()
            now = datetime.now(timezone.utc).isoformat()
            node_exec_id = add_workflow_node_execution(
                execution_id=execution_id,
                node_id=node_id,
                node_type=node_type,
                input_json=input_json_str,
            )
            if node_exec_id:
                update_workflow_node_execution(node_exec_id, status="running", started_at=now)

            cls._update_node_state(execution_id, node_id, "running")

            # Inject execution_id so node executors can access it via input_msg
            if input_msg.metadata is None:
                input_msg.metadata = {}
            input_msg.metadata["_execution_id"] = execution_id

            # Per-node timeout (independent of global workflow timeout)
            node_timeout_seconds = node_config.get("node_timeout_seconds")

            # Dispatch with retry
            output_msg = None
            last_error = None
            attempts = 0
            max_attempts = 1 + retry_max

            while attempts < max_attempts:
                attempts += 1
                try:
                    if node_timeout_seconds:
                        output_msg = cls._dispatch_node_with_timeout(
                            node_id, node_type, node_config, input_msg, node_timeout_seconds
                        )
                    else:
                        output_msg = cls._dispatch_node(node_id, node_type, node_config, input_msg)
                    last_error = None
                    break  # Success
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        f"Workflow {execution_id}, node {node_id}: "
                        f"attempt {attempts}/{max_attempts} failed: {e}",
                        exc_info=True,
                    )
                    if attempts < max_attempts:
                        # Compute delay based on backoff strategy
                        if backoff_strategy == "fixed":
                            delay = retry_backoff
                        elif backoff_strategy == "linear":
                            delay = retry_backoff * attempts
                        else:
                            # exponential (default)
                            delay = retry_backoff * (2 ** (attempts - 1))
                        time.sleep(delay)

            # Handle result
            now = datetime.now(timezone.utc).isoformat()

            if last_error is not None:
                # Node failed after all retries
                logger.error(
                    f"Workflow {execution_id}, node {node_id}: "
                    f"failed after {attempts} attempt(s): {last_error}"
                )
                cls._update_node_state(execution_id, node_id, "failed")
                if node_exec_id:
                    error_detail = last_error
                    if attempts > 1:
                        error_detail = f"{last_error} (after {attempts} attempts)"
                    update_workflow_node_execution(
                        node_exec_id,
                        status="failed",
                        error=error_detail,
                        ended_at=now,
                    )

                # Apply error mode
                if error_mode == NodeErrorMode.STOP or error_mode == "stop":
                    workflow_failed = True
                    workflow_error = f"Node {node_id} failed: {last_error}"
                    # Mark all downstream nodes as skipped
                    cls._mark_downstream_skipped(node_id, successors, skipped_nodes)
                    break

                elif error_mode == NodeErrorMode.CONTINUE or error_mode == "continue":
                    # Skip downstream dependents of this failed node
                    cls._mark_downstream_skipped(node_id, successors, skipped_nodes)
                    continue

                elif (
                    error_mode == NodeErrorMode.CONTINUE_WITH_ERROR
                    or error_mode == "continue_with_error"
                ):
                    # Create error message as output so downstream nodes receive error data
                    error_output = WorkflowMessage(
                        content_type="error",
                        text=f"Error in node {node_id}: {last_error}",
                        data={"error": last_error, "node_id": node_id, "attempts": attempts},
                        metadata={"source_node_id": node_id, "error": "true"},
                    )
                    node_outputs[node_id] = error_output
                    if node_exec_id:
                        update_workflow_node_execution(
                            node_exec_id,
                            output_json=error_output.model_dump_json(),
                        )
                    continue
            else:
                # Node succeeded
                if output_msg is None:
                    output_msg = WorkflowMessage()
                node_outputs[node_id] = output_msg
                cls._update_node_state(execution_id, node_id, "completed")
                if node_exec_id:
                    update_workflow_node_execution(
                        node_exec_id,
                        status="completed",
                        output_json=output_msg.model_dump_json(),
                        ended_at=now,
                    )

                # Edge-aware branch routing: when a conditional node returns a
                # branch result, skip non-matching branch targets and their
                # downstream nodes.
                branch_label = (output_msg.metadata or {}).get("branch")
                if branch_label and node_type == "conditional":
                    for edge in edges_list:
                        if edge.get("source") != node_id:
                            continue
                        edge_handle = edge.get("sourceHandle")
                        # Only filter edges with an explicit non-None sourceHandle.
                        # Edges without sourceHandle (or None) are unconditional
                        # and always execute (backward compatibility).
                        if edge_handle is not None and edge_handle != branch_label:
                            target_id = edge["target"]
                            if target_id not in skipped_nodes:
                                skipped_nodes.add(target_id)
                                cls._mark_downstream_skipped(target_id, successors, skipped_nodes)

        # Write DB records for any remaining skipped nodes
        for remaining_id in skipped_nodes:
            # Only write if we haven't already written a record for this node
            existing_nodes = get_workflow_node_executions(execution_id)
            existing_ids = {n["node_id"] for n in existing_nodes}
            if remaining_id not in existing_ids:
                now_skip = datetime.now(timezone.utc).isoformat()
                row_id = add_workflow_node_execution(
                    execution_id=execution_id,
                    node_id=remaining_id,
                    node_type=nodes[remaining_id].get("type", "unknown"),
                    input_json=None,
                )
                if row_id:
                    update_workflow_node_execution(
                        row_id, status="skipped", started_at=now_skip, ended_at=now_skip
                    )

        # Finalize workflow execution
        now = datetime.now(timezone.utc).isoformat()
        if workflow_failed:
            cls._update_status(execution_id, "failed", error=workflow_error)
            # Get last node output if available
            last_output = None
            if topo_order and topo_order[-1] in node_outputs:
                last_output = node_outputs[topo_order[-1]].model_dump_json()
            update_workflow_execution(
                execution_id,
                status="failed",
                error=workflow_error,
                output_json=last_output,
                ended_at=now,
            )
        else:
            last_output = cls._collect_results(topo_order, node_outputs)
            cls._update_status(execution_id, "completed")
            update_workflow_execution(
                execution_id,
                status="completed",
                output_json=last_output,
                ended_at=now,
            )

        final_status = "failed" if workflow_failed else "completed"
        logger.info(f"Workflow execution finished: {execution_id} (status={final_status})")

        # Fire completion triggers (lazy import to avoid circular dependency)
        try:
            from .workflow_trigger_service import WorkflowTriggerService

            output_data = None
            if last_output:
                try:
                    output_data = json.loads(last_output)
                except (json.JSONDecodeError, TypeError):
                    pass  # Intentionally silenced: malformed data handled gracefully
            WorkflowTriggerService.on_execution_complete(
                "workflow", workflow_id, final_status, output=output_data
            )
        except Exception as e:
            logger.error(f"Error firing completion triggers for {execution_id}: {e}", exc_info=True)

        cls._schedule_cleanup(execution_id)

    @classmethod
    def _schedule_cleanup(cls, execution_id: str) -> None:
        """Schedule removal of in-memory tracking after 5 minutes.

        Uses APScheduler when available so the job survives daemon-thread teardown.
        Falls back to a daemon threading.Timer when the scheduler is not running
        (e.g. during tests).
        """
        try:
            from .scheduler_service import SchedulerService

            if SchedulerService._scheduler:
                SchedulerService._scheduler.add_job(
                    func=cls._cleanup_execution,
                    trigger="date",
                    run_date=datetime.now() + timedelta(seconds=300),
                    args=[execution_id],
                    id=f"wf_ttl_{execution_id}",
                    replace_existing=True,
                )
                return
        except Exception:
            pass  # Intentionally silenced: failure is non-critical
        # Fallback: daemon timer (used when scheduler is unavailable)
        timer = threading.Timer(300, cls._cleanup_execution, args=[execution_id])
        timer.daemon = True
        timer.start()

    @classmethod
    def _mark_downstream_skipped(
        cls, node_id: str, successors: Dict[str, set], skipped_nodes: set
    ) -> None:
        """Recursively mark all downstream nodes as skipped."""
        for succ_id in successors.get(node_id, set()):
            if succ_id not in skipped_nodes:
                skipped_nodes.add(succ_id)
                cls._mark_downstream_skipped(succ_id, successors, skipped_nodes)

    @classmethod
    def _merge_messages(cls, messages: List[WorkflowMessage]) -> WorkflowMessage:
        """Merge multiple WorkflowMessages into a single message.

        Combines text fields with newlines, merges data dicts, combines metadata.
        """
        merged_text_parts = []
        merged_data = {}
        merged_metadata = {}
        last_exit_code = None
        last_stdout = None
        last_stderr = None

        for msg in messages:
            if msg.text:
                merged_text_parts.append(msg.text)
            if msg.data:
                merged_data.update(msg.data)
            if msg.metadata:
                merged_metadata.update(msg.metadata)
            if msg.exit_code is not None:
                last_exit_code = msg.exit_code
            if msg.stdout is not None:
                last_stdout = msg.stdout
            if msg.stderr is not None:
                last_stderr = msg.stderr

        return WorkflowMessage(
            content_type="merged",
            text="\n".join(merged_text_parts) if merged_text_parts else None,
            data=merged_data if merged_data else None,
            metadata=merged_metadata,
            exit_code=last_exit_code,
            stdout=last_stdout,
            stderr=last_stderr,
        )

    # =========================================================================
    # Node Dispatchers — delegate to NodeExecutor
    #
    # These methods are kept on WorkflowExecutionService so that existing
    # test patches (e.g. monkeypatch.setattr(WorkflowExecutionService,
    # "_execute_command_node", ...)) continue to work. The _dispatch_node
    # method uses getattr(cls, handler_name) which resolves these methods,
    # allowing tests to override them on this class.
    # =========================================================================

    @classmethod
    def _dispatch_node(
        cls,
        node_id: str,
        node_type: str,
        node_config: dict,
        input_msg: WorkflowMessage,
    ) -> WorkflowMessage:
        """Dispatch execution to the appropriate node handler."""
        handler_name = cls.NODE_DISPATCHERS.get(node_type)
        if not handler_name:
            raise ValueError(f"Unknown node type: {node_type}")

        handler = getattr(cls, handler_name)
        return handler(node_id, node_config, input_msg)

    @classmethod
    def _dispatch_node_with_timeout(
        cls,
        node_id: str,
        node_type: str,
        node_config: dict,
        input_msg: WorkflowMessage,
        timeout_seconds: float,
    ) -> WorkflowMessage:
        """Dispatch a node with a per-node wall-clock timeout.

        Runs the handler in a daemon thread and joins it with the given timeout.
        Raises RuntimeError if the node does not complete within the timeout.
        """
        result: list = [None, None]  # [output_msg, exception]

        def _run() -> None:
            try:
                result[0] = cls._dispatch_node(node_id, node_type, node_config, input_msg)
            except Exception as exc:
                result[1] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            raise RuntimeError(
                f"Node {node_id} (type={node_type}) timed out after {timeout_seconds}s"
            )
        if result[1] is not None:
            raise result[1]
        return result[0]

    @classmethod
    def _execute_trigger_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a trigger node — delegates to NodeExecutor."""
        return NodeExecutor._execute_trigger_node(node_id, node_config, input_msg)

    @classmethod
    def _execute_skill_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a skill node — delegates to NodeExecutor."""
        return NodeExecutor._execute_skill_node(node_id, node_config, input_msg)

    @classmethod
    def _execute_command_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a command node — delegates to NodeExecutor."""
        return NodeExecutor._execute_command_node(node_id, node_config, input_msg)

    @classmethod
    def _execute_agent_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute an agent node — delegates to NodeExecutor."""
        return NodeExecutor._execute_agent_node(node_id, node_config, input_msg)

    @classmethod
    def _execute_script_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a script node — delegates to NodeExecutor."""
        return NodeExecutor._execute_script_node(node_id, node_config, input_msg)

    @classmethod
    def _execute_conditional_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a conditional node — delegates to NodeExecutor."""
        return NodeExecutor._execute_conditional_node(node_id, node_config, input_msg)

    @classmethod
    def _execute_transform_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a transform node — delegates to NodeExecutor."""
        return NodeExecutor._execute_transform_node(node_id, node_config, input_msg)

    @classmethod
    def _execute_approval_gate_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute an approval gate node — delegates to NodeExecutor."""
        return NodeExecutor._execute_approval_gate_node(node_id, node_config, input_msg)

    # =========================================================================
    # Approve / Reject API
    # =========================================================================

    @classmethod
    def approve_node(cls, execution_id: str, node_id: str, resolved_by: str = None) -> bool:
        """Approve a pending approval gate node.

        Sets the threading.Event to resume workflow execution and updates DB
        state to 'approved'. Returns True if the approval was successful.
        """
        from ..db.workflows import update_workflow_approval_state

        approval_key = (execution_id, node_id)

        with cls._approval_lock:
            event = cls._approval_events.get(approval_key)
            if not event:
                return False

        # Update DB state
        update_workflow_approval_state(execution_id, node_id, "approved", resolved_by)

        # Set the event to resume the waiting thread
        event.set()
        return True

    @classmethod
    def reject_node(cls, execution_id: str, node_id: str, resolved_by: str = None) -> bool:
        """Reject a pending approval gate node.

        Sets a rejection flag and the threading.Event so the approval gate node
        sees the rejection and raises an error, aborting downstream nodes.
        Returns True if the rejection was successful.
        """
        from ..db.workflows import update_workflow_approval_state

        approval_key = (execution_id, node_id)

        with cls._approval_lock:
            event = cls._approval_events.get(approval_key)
            if not event:
                return False
            cls._rejection_flags[approval_key] = True

        # Update DB state
        update_workflow_approval_state(execution_id, node_id, "rejected", resolved_by)

        # Set the event to resume the waiting thread (it will check rejection flag)
        event.set()
        return True
