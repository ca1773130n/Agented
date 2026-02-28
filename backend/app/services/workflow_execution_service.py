"""Workflow execution service — DAG execution engine with topological sort, node dispatch,
error handling, retry, and timeout."""

import graphlib
import json
import logging
import os
import shlex
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..models.workflow import NodeErrorMode, WorkflowMessage

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

    DEFAULT_TIMEOUT_SECONDS = 1800  # 30 minutes

    # Node type dispatcher map
    NODE_DISPATCHERS = {
        "trigger": "_execute_trigger_node",
        "skill": "_execute_skill_node",
        "command": "_execute_command_node",
        "agent": "_execute_agent_node",
        "script": "_execute_script_node",
        "conditional": "_execute_conditional_node",
        "transform": "_execute_transform_node",
    }

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
    def _update_status(cls, execution_id: str, status: str, error: str = None):
        """Update in-memory execution status."""
        with cls._lock:
            entry = cls._executions.get(execution_id)
            if entry:
                entry["status"] = status
                if error:
                    entry["error"] = error

    @classmethod
    def _update_node_state(cls, execution_id: str, node_id: str, status: str):
        """Update in-memory node state."""
        with cls._lock:
            entry = cls._executions.get(execution_id)
            if entry:
                entry.setdefault("node_states", {})[node_id] = status

    @classmethod
    def cleanup_stale_executions(cls):
        """Mark any DB-persisted 'running' executions as failed.

        Called once at server startup to recover from unclean shutdowns where
        in-memory execution state was lost but DB records were left as 'running'.
        """
        from ..db.workflows import get_running_workflow_executions, update_workflow_execution

        stale = get_running_workflow_executions()
        if not stale:
            return
        now = datetime.now(timezone.utc).isoformat()
        for execution in stale:
            execution_id = execution["id"]
            update_workflow_execution(
                execution_id,
                status="failed",
                error="Server restarted while execution was running",
                ended_at=now,
            )
            logger.warning("Marked stale workflow execution as failed on startup: %s", execution_id)

    @classmethod
    def _cleanup_execution(cls, execution_id: str):
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
    ):
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

        # Build adjacency: predecessor map (node_id -> set of predecessor node_ids)
        predecessors: Dict[str, set] = {nid: set() for nid in nodes}
        for edge in edges_list:
            source = edge["source"]
            target = edge["target"]
            predecessors[target].add(source)

        # Build successor map for skip propagation
        successors: Dict[str, set] = {nid: set() for nid in nodes}
        for edge in edges_list:
            successors[edge["source"]].add(edge["target"])

        # Topological sort
        try:
            ts = graphlib.TopologicalSorter(predecessors)
            topo_order = list(ts.static_order())
        except graphlib.CycleError as e:
            error_msg = f"Graph cycle detected: {e}"
            logger.error(f"Workflow {execution_id}: {error_msg}")
            cls._update_status(execution_id, "failed", error=error_msg)
            now = datetime.now(timezone.utc).isoformat()
            update_workflow_execution(execution_id, status="failed", error=error_msg, ended_at=now)
            cls._schedule_cleanup(execution_id)
            return

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
                        # Exponential backoff
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
            # Get the last node's output as the workflow output
            last_output = None
            for nid in reversed(topo_order):
                if nid in node_outputs:
                    last_output = node_outputs[nid].model_dump_json()
                    break
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
                    pass
            WorkflowTriggerService.on_execution_complete(
                "workflow", workflow_id, final_status, output=output_data
            )
        except Exception as e:
            logger.error(f"Error firing completion triggers for {execution_id}: {e}", exc_info=True)

        cls._schedule_cleanup(execution_id)

    @classmethod
    def _schedule_cleanup(cls, execution_id: str):
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
            pass
        # Fallback: daemon timer (used when scheduler is unavailable)
        timer = threading.Timer(300, cls._cleanup_execution, args=[execution_id])
        timer.daemon = True
        timer.start()

    @classmethod
    def _mark_downstream_skipped(cls, node_id: str, successors: Dict[str, set], skipped_nodes: set):
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
    # Node Dispatchers
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

        def _run():
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
        """Execute a trigger node (entry point).

        Pass-through: returns input as-is, or creates a message from config data.
        """
        if "data" in node_config:
            return WorkflowMessage(
                content_type="trigger",
                data=node_config["data"],
                metadata={"source_node_id": node_id},
            )
        # Pass through input
        return WorkflowMessage(
            content_type="trigger",
            text=input_msg.text,
            data=input_msg.data,
            metadata={**input_msg.metadata, "source_node_id": node_id},
        )

    @classmethod
    def _execute_skill_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a skill node (stub).

        Real skill invocation deferred to when skills integration is built.
        """
        skill_name = node_config.get("skill_name", "unknown")
        return WorkflowMessage(
            content_type="text",
            text=f"[skill:{skill_name}] executed",
            metadata={"source_node_id": node_id},
        )

    @classmethod
    def _execute_command_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a shell command node.

        Runs the command via subprocess.run() with a timeout. Returns stdout, stderr,
        and exit code in a WorkflowMessage.
        """
        command = node_config.get("command")
        if not command:
            raise ValueError(f"Command node {node_id} has no 'command' in config")

        timeout = node_config.get("timeout", 60)
        cwd = node_config.get("cwd")

        try:
            result = subprocess.run(
                shlex.split(command),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            stdout = result.stdout[:10000] if result.stdout else ""
            stderr = result.stderr[:10000] if result.stderr else ""

            if result.returncode != 0:
                raise RuntimeError(
                    f"Command exited with code {result.returncode}: "
                    f"{stderr[:200] if stderr else 'no stderr'}"
                )

            return WorkflowMessage(
                content_type="command_output",
                text=stdout.strip(),
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                metadata={"source_node_id": node_id, "command": command},
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out after {timeout}s: {command[:100]}")

    @classmethod
    def _execute_agent_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute an agent node (stub).

        Real agent invocation would call ExecutionService. Deferred to agent integration.
        """
        agent_id = node_config.get("agent_id", "unknown")
        return WorkflowMessage(
            content_type="text",
            text=f"[agent:{agent_id}] executed",
            metadata={"source_node_id": node_id},
        )

    @classmethod
    def _execute_script_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a script node.

        Writes script content to a temp file, runs it via subprocess,
        and returns the output.
        """
        script = node_config.get("script")
        if not script:
            raise ValueError(f"Script node {node_id} has no 'script' in config")

        timeout = node_config.get("timeout", 60)
        interpreter = node_config.get("interpreter", "python3")

        tmp_file = None
        try:
            # Write script to temp file
            suffix = ".py" if "python" in interpreter else ".sh"
            tmp_file = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
            tmp_file.write(script)
            tmp_file.flush()
            tmp_file.close()

            result = subprocess.run(
                [interpreter, tmp_file.name],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = result.stdout[:10000] if result.stdout else ""
            stderr = result.stderr[:10000] if result.stderr else ""

            if result.returncode != 0:
                raise RuntimeError(
                    f"Script exited with code {result.returncode}: "
                    f"{stderr[:200] if stderr else 'no stderr'}"
                )

            return WorkflowMessage(
                content_type="script_output",
                text=stdout.strip(),
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                metadata={"source_node_id": node_id},
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Script timed out after {timeout}s")
        finally:
            # Clean up temp file
            if tmp_file and os.path.exists(tmp_file.name):
                try:
                    os.unlink(tmp_file.name)
                except OSError as e:
                    logger.warning("Failed to delete temp script file %s: %s", tmp_file.name, e)

    @classmethod
    def _execute_conditional_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a conditional node.

        Evaluates a condition against the input message and returns a boolean result.
        Supported conditions: has_text, exit_code_zero, contains.
        """
        condition = node_config.get("condition", "has_text")
        result = False

        if condition == "has_text":
            result = bool(input_msg.text)
        elif condition == "exit_code_zero":
            result = input_msg.exit_code == 0
        elif condition == "contains":
            value = node_config.get("value", "")
            result = value in (input_msg.text or "")
        else:
            logger.warning(f"Unknown condition type: {condition}")

        branch = "true" if result else "false"
        return WorkflowMessage(
            content_type="conditional",
            data={"result": result, "branch": branch},
            text=input_msg.text,
            metadata={"source_node_id": node_id, "condition": condition, "branch": branch},
        )

    @classmethod
    def _execute_transform_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute a transform node.

        Applies a transformation to the input message.
        Supported types: extract_field, template, json_parse, uppercase, lowercase.
        """
        transform_type = node_config.get("transform_type", "passthrough")

        if transform_type == "extract_field":
            field = node_config.get("field", "")
            data = input_msg.data or {}
            value = data.get(field)
            return WorkflowMessage(
                content_type="text",
                text=str(value) if value is not None else None,
                data={"field": field, "value": value},
                metadata={"source_node_id": node_id, "transform": "extract_field"},
            )

        elif transform_type == "template":
            template = node_config.get("template", "")
            # Format with input message fields
            try:
                formatted = template.format(
                    text=input_msg.text or "",
                    data=input_msg.data or {},
                    stdout=input_msg.stdout or "",
                    stderr=input_msg.stderr or "",
                    exit_code=input_msg.exit_code,
                )
            except (KeyError, IndexError, ValueError):
                formatted = template
            return WorkflowMessage(
                content_type="text",
                text=formatted,
                metadata={"source_node_id": node_id, "transform": "template"},
            )

        elif transform_type == "json_parse":
            try:
                parsed = json.loads(input_msg.text or "{}")
                return WorkflowMessage(
                    content_type="json",
                    data=parsed if isinstance(parsed, dict) else {"value": parsed},
                    metadata={"source_node_id": node_id, "transform": "json_parse"},
                )
            except (json.JSONDecodeError, TypeError):
                raise ValueError(f"Cannot parse input text as JSON in node {node_id}")

        elif transform_type == "uppercase":
            return WorkflowMessage(
                content_type="text",
                text=(input_msg.text or "").upper(),
                metadata={"source_node_id": node_id, "transform": "uppercase"},
            )

        elif transform_type == "lowercase":
            return WorkflowMessage(
                content_type="text",
                text=(input_msg.text or "").lower(),
                metadata={"source_node_id": node_id, "transform": "lowercase"},
            )

        else:
            # Passthrough
            return WorkflowMessage(
                content_type=input_msg.content_type,
                text=input_msg.text,
                data=input_msg.data,
                metadata={**input_msg.metadata, "source_node_id": node_id},
                exit_code=input_msg.exit_code,
                stdout=input_msg.stdout,
                stderr=input_msg.stderr,
            )
