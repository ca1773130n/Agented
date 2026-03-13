"""Node executor module for workflow DAG execution.

Contains individual node type handlers (trigger, skill, command, agent, script,
conditional, transform, approval_gate) and the dispatch/timeout logic.
"""

import json
import logging
import os
import shlex
import subprocess
import tempfile
import threading

from ..models.workflow import WorkflowMessage
from .workflow_expression_evaluator import evaluate_condition

logger = logging.getLogger(__name__)


class NodeExecutor:
    """Dispatches and executes individual workflow node types.

    All methods are classmethods that take node_id, node_config, and input_msg
    as parameters, matching the signature expected by WorkflowExecutionService.
    """

    # Node type dispatcher map
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

    @classmethod
    def dispatch_node(
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
    def dispatch_node_with_timeout(
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
                result[0] = cls.dispatch_node(node_id, node_type, node_config, input_msg)
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
        """Execute an agent node via OrchestrationService with fallback chain.

        Reads fallback_chain and routing_rules from node_config to determine which
        model/account to use. Delegates execution to OrchestrationService.execute_with_fallback()
        which handles rate limits, budget checks, and account rotation.

        If routing_rules are configured and diff size is available, the fallback chain
        is filtered to the appropriate tier (cheap vs expensive) before execution.
        """
        from .orchestration_service import ExecutionStatus, OrchestrationService

        agent_id = node_config.get("agent_id", "unknown")
        trigger_id = node_config.get("trigger_id")

        # Read fallback chain and routing rules from config
        fallback_chain = node_config.get("fallback_chain", [])
        routing_rules = node_config.get("routing_rules")

        # Determine diff size from input message data
        input_data = input_msg.data or {}
        diff_size = input_data.get("diff_size", 0)
        pr_data = input_data.get("pr", {})
        if isinstance(pr_data, dict):
            diff_size = diff_size or pr_data.get("lines_changed", 0)

        # Apply routing rules to filter fallback chain by tier
        effective_chain = list(fallback_chain)
        if routing_rules and diff_size and effective_chain:
            threshold = routing_rules.get("diff_size_threshold", 500)
            if diff_size < threshold:
                target_tier = routing_rules.get("small_diff_tier", "cheap")
            else:
                target_tier = routing_rules.get("large_diff_tier", "expensive")

            filtered = [e for e in effective_chain if e.get("tier") == target_tier]
            if filtered:
                effective_chain = filtered
            # If filter produces empty list, use full chain (graceful fallback)

        # Build message text from input
        message_text = input_msg.text or ""
        if not message_text and input_data:
            message_text = json.dumps(input_data, default=str)[:5000]

        # Build synthetic trigger dict for OrchestrationService
        trigger_dict = {
            "id": trigger_id or f"wf-agent-{node_id}",
            "name": f"workflow-agent-{agent_id}",
            "backend_type": "claude",  # default, overridden by chain entries
            "agent_id": agent_id,
        }

        # Build event data from input message
        event_data = {
            "node_id": node_id,
            "agent_id": agent_id,
            **(input_data or {}),
        }

        # If we have an explicit fallback chain, override the default chain lookup
        # by setting the chain entries on the trigger dict
        if effective_chain:
            trigger_dict["_fallback_chain_override"] = effective_chain

        result = OrchestrationService.execute_with_fallback(
            trigger_dict, message_text, event_data, "workflow"
        )

        if result.status == ExecutionStatus.CHAIN_EXHAUSTED:
            raise RuntimeError(
                f"Agent node {node_id}: all fallback chain providers exhausted "
                f"({result.detail or 'no detail'})"
            )

        if result.status == ExecutionStatus.BUDGET_BLOCKED:
            raise RuntimeError(
                f"Agent node {node_id}: budget blocked ({result.detail or 'no detail'})"
            )

        if result.status == ExecutionStatus.LAUNCH_FAILED:
            raise RuntimeError(f"Agent node {node_id}: execution launch failed")

        # DISPATCHED: execution started successfully
        return WorkflowMessage(
            content_type="agent_output",
            text=f"Agent {agent_id} execution dispatched: {result.execution_id}",
            data={
                "execution_id": result.execution_id,
                "agent_id": agent_id,
                "status": result.status.value,
            },
            metadata={
                "source_node_id": node_id,
                "execution_id": result.execution_id or "",
                "agent_id": agent_id,
            },
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
        Supported conditions: has_text, exit_code_zero, contains, expression.

        The 'expression' condition type uses the safe AST-based evaluator to evaluate
        rich expressions against the input data (e.g., pr.lines_changed > 500).
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
        elif condition == "expression":
            expression = node_config.get("expression", "")
            if not expression:
                logger.warning(f"Expression condition on node {node_id} has empty expression")
                result = False
            else:
                # Build context from input_msg.data (upstream node's output data)
                context = input_msg.data or {}
                try:
                    result = evaluate_condition(expression, context)
                except ValueError as e:
                    logger.error(
                        f"Expression evaluation error on node {node_id}: {e}", exc_info=True
                    )
                    result = False
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

    # =========================================================================
    # Approval Gate Node
    # =========================================================================

    @classmethod
    def _execute_approval_gate_node(
        cls, node_id: str, node_config: dict, input_msg: WorkflowMessage
    ) -> WorkflowMessage:
        """Execute an approval gate node.

        Pauses workflow execution via threading.Event.wait() until an approve or
        reject API call is made, or the timeout expires. Follows the proven
        TeamExecutionService._execute_human_in_loop pattern.

        The execution_id is obtained from input_msg.metadata["_execution_id"],
        which is injected by _run_workflow before dispatch.

        NOTE: This method accesses WorkflowExecutionService class-level state
        (_approval_events, _approval_lock, _rejection_flags, _update_node_state,
        _update_status) via a lazy import to avoid circular dependencies.
        """
        # Lazy import to access class-level approval state on WorkflowExecutionService
        from .workflow_execution_service import WorkflowExecutionService

        from ..db.workflows import add_workflow_approval_state, update_workflow_approval_state

        timeout = node_config.get("timeout", 1800)

        # Get execution_id from metadata (injected by _run_workflow Part B)
        execution_id = (input_msg.metadata or {}).get("_execution_id")
        if not execution_id:
            raise RuntimeError(
                "execution_id not available in input_msg.metadata -- _run_workflow must inject it"
            )

        # Create approval event
        approval_event = threading.Event()
        approval_key = (execution_id, node_id)

        # Register in class-level approval events dict
        with WorkflowExecutionService._approval_lock:
            WorkflowExecutionService._approval_events[approval_key] = approval_event

        # Persist to DB
        add_workflow_approval_state(execution_id, node_id, timeout)

        # Update node state to pending_approval (triggers SSE via existing mechanism)
        WorkflowExecutionService._update_node_state(execution_id, node_id, "pending_approval")

        # Also update overall execution status to pending_approval
        WorkflowExecutionService._update_status(execution_id, "pending_approval")

        logger.info(
            f"Approval gate: waiting for approval on execution={execution_id}, "
            f"node={node_id}, timeout={timeout}s"
        )

        # Wait for approval or timeout
        approved = approval_event.wait(timeout=timeout)

        # Clean up event from registry
        with WorkflowExecutionService._approval_lock:
            WorkflowExecutionService._approval_events.pop(approval_key, None)

        if not approved:
            # Timeout
            update_workflow_approval_state(execution_id, node_id, "timed_out")
            WorkflowExecutionService._update_status(execution_id, "running")
            raise RuntimeError(
                f"Approval gate timed out after {timeout}s "
                f"(execution={execution_id}, node={node_id})"
            )

        # Check if rejected
        with WorkflowExecutionService._approval_lock:
            was_rejected = WorkflowExecutionService._rejection_flags.pop(approval_key, False)

        if was_rejected:
            WorkflowExecutionService._update_status(execution_id, "running")
            raise RuntimeError(f"Approval gate rejected (execution={execution_id}, node={node_id})")

        # Approved -- restore running status and pass through
        WorkflowExecutionService._update_status(execution_id, "running")
        logger.info(f"Approval gate: approved for execution={execution_id}, node={node_id}")

        return WorkflowMessage(
            content_type=input_msg.content_type or "approval_gate",
            text=input_msg.text,
            data=input_msg.data,
            metadata={
                **(input_msg.metadata or {}),
                "source_node_id": node_id,
                "approval_status": "approved",
            },
            exit_code=input_msg.exit_code,
            stdout=input_msg.stdout,
            stderr=input_msg.stderr,
        )
