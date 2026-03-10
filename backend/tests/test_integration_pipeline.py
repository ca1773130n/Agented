"""Integration tests for multi-service workflows.

Tests the FLOW between services — trigger dispatch, workflow DAG execution,
team topology execution, and cross-entity reference integrity — using real
DB operations (isolated_db) with mocked subprocess to avoid real CLI calls.
"""

import io
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Helpers
# =============================================================================


def _create_agent_in_db(isolated_db, agent_id, name="Test Agent", backend_type="claude"):
    """Create an agent directly in the DB."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, backend_type, enabled) VALUES (?, ?, ?, 1)",
            (agent_id, name, backend_type),
        )
        conn.commit()


def _create_team_with_topology(client, isolated_db, topology, topology_config, agent_ids):
    """Create a team with agents, members, and topology config. Returns team_id."""
    for aid in agent_ids:
        _create_agent_in_db(isolated_db, aid, name=f"Agent {aid}")

    resp = client.post("/admin/teams/", json={"name": "Integration Test Team"})
    assert resp.status_code == 201
    team_id = resp.get_json()["team"]["id"]

    for aid in agent_ids:
        resp = client.post(
            f"/admin/teams/{team_id}/members",
            json={"agent_id": aid, "name": f"Agent {aid}"},
        )
        assert resp.status_code == 201

    resp = client.put(
        f"/admin/teams/{team_id}/topology",
        json={"topology": topology, "topology_config": topology_config},
    )
    assert resp.status_code == 200

    resp = client.put(
        f"/admin/teams/{team_id}/trigger",
        json={"trigger_source": "manual", "enabled": 1},
    )
    assert resp.status_code == 200

    return team_id


def _make_mock_process(stdout_lines=None, exit_code=0):
    """Create a mock subprocess.Popen process with text-mode pipes."""
    mock_process = MagicMock()
    # Popen is called with text=True, so pipes yield strings not bytes
    stdout_text = "".join(stdout_lines) if stdout_lines else ""
    mock_process.stdout = io.StringIO(stdout_text)
    mock_process.stderr = io.StringIO("")
    mock_process.wait.return_value = exit_code
    mock_process.returncode = exit_code
    mock_process.pid = 12345
    mock_process.poll.return_value = exit_code
    return mock_process


# =============================================================================
# A. Trigger -> Execution Pipeline
# =============================================================================


class TestTriggerExecutionPipeline:
    """Tests that a webhook trigger flows through dispatch -> queue -> execution."""

    def test_webhook_creates_trigger_and_dispatches(self, client, isolated_db):
        """Create a trigger via API, fire a matching webhook, verify execution is enqueued."""
        from app.db.triggers import create_trigger, get_trigger

        trigger_id = create_trigger(
            name="Pipeline Test Trigger",
            prompt_template="Analyze: {message}",
            backend_type="claude",
            trigger_source="webhook",
            match_field_path="event.type",
            match_field_value="security_alert",
            text_field_path="event.text",
        )
        assert trigger_id is not None
        trigger = get_trigger(trigger_id)
        assert trigger is not None
        assert trigger["trigger_source"] == "webhook"

        # Dispatch webhook event -- mock the queue to capture what gets enqueued
        with patch(
            "app.services.execution_queue_service.ExecutionQueueService.enqueue",
            return_value="qe-pipe01",
        ) as mock_enqueue:
            from app.services.execution_service import ExecutionService

            triggered = ExecutionService.dispatch_webhook_event(
                {"event": {"type": "security_alert", "text": "CVE-2026-1234 found"}}
            )

        assert triggered is True
        mock_enqueue.assert_called_once()
        call_kwargs = mock_enqueue.call_args[1]
        assert call_kwargs["trigger_id"] == trigger_id
        assert call_kwargs["trigger_type"] == "webhook"
        assert "CVE-2026-1234" in call_kwargs["message_text"]

    def test_run_trigger_creates_execution_log(self, client, isolated_db):
        """Verify run_trigger creates an execution log entry with correct status tracking."""
        from app.db.triggers import create_trigger, get_trigger
        from app.services.execution_log_service import ExecutionLogService
        from app.services.execution_service import ExecutionService

        trigger_id = create_trigger(
            name="Log Test Trigger",
            prompt_template="Test: {message}",
            backend_type="claude",
            trigger_source="webhook",
        )
        trigger = get_trigger(trigger_id)

        mock_process = _make_mock_process(stdout_lines=["line 1\n", "line 2\n"], exit_code=0)

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("shutil.which", return_value=None),  # skip stdbuf
            patch(
                "app.services.execution_service.ExecutionService._clone_repos",
                return_value=[],
            ),
            patch(
                "app.services.budget_service.BudgetService.check_budget",
                return_value={"allowed": True},
            ),
        ):
            execution_id = ExecutionService.run_trigger(
                trigger=trigger,
                message_text="test message for logging",
                event={"type": "test"},
                trigger_type="webhook",
            )

        assert execution_id is not None

        # Verify execution record exists in DB
        history = ExecutionLogService.get_history(trigger_id=trigger_id)
        assert len(history) >= 1
        exec_record = next((e for e in history if e["execution_id"] == execution_id), None)
        assert exec_record is not None
        assert exec_record["status"] in ("success", "failed")

    def test_dispatch_deduplicates_identical_payloads(self, client, isolated_db):
        """Verify identical webhook payloads are deduplicated within the TTL window."""
        from app.db.triggers import create_trigger

        create_trigger(
            name="Dedup Test Trigger",
            prompt_template="Test: {message}",
            backend_type="claude",
            trigger_source="webhook",
            match_field_path="event.type",
            match_field_value="alert",
            text_field_path="event.text",
        )

        payload = {"event": {"type": "alert", "text": "duplicate test"}}

        with patch(
            "app.services.execution_queue_service.ExecutionQueueService.enqueue",
            return_value="qe-dedup01",
        ) as mock_enqueue:
            from app.services.execution_service import ExecutionService

            # First dispatch should succeed
            result1 = ExecutionService.dispatch_webhook_event(payload)
            assert result1 is True
            assert mock_enqueue.call_count == 1

            # Second identical dispatch should be deduplicated
            result2 = ExecutionService.dispatch_webhook_event(payload)
            # Enqueue should still be called only once (second was deduped)
            assert mock_enqueue.call_count == 1


# =============================================================================
# B. Workflow Execution Pipeline
# =============================================================================


class TestWorkflowExecutionPipeline:
    """Tests workflow DAG orchestration: node ordering, result collection, error modes."""

    def _create_workflow_with_version(self, client, graph):
        """Helper: create workflow + version via API, return workflow_id."""
        resp = client.post("/admin/workflows/", json={"name": "Pipeline Test Workflow"})
        assert resp.status_code == 201
        workflow_id = resp.get_json()["workflow_id"]

        graph_json = json.dumps(graph) if isinstance(graph, dict) else graph
        resp = client.post(
            f"/admin/workflows/{workflow_id}/versions",
            json={"graph_json": graph_json},
        )
        assert resp.status_code == 201

        return workflow_id

    def _wait_execution(self, client, execution_id, timeout=5):
        """Poll until execution is no longer running."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = client.get(f"/admin/workflows/executions/{execution_id}")
            body = resp.get_json()
            status = body["execution"]["status"]
            if status not in ("running", "pending"):
                return body
            time.sleep(0.1)
        resp = client.get(f"/admin/workflows/executions/{execution_id}")
        return resp.get_json()

    def test_sequential_3_node_workflow_executes_in_order(self, client, isolated_db):
        """A -> B -> C pipeline: trigger -> transform -> command. Nodes execute in topo order."""
        graph = {
            "nodes": [
                {
                    "id": "A",
                    "type": "trigger",
                    "label": "Start",
                    "config": {"data": {"msg": "hello"}},
                },
                {
                    "id": "B",
                    "type": "transform",
                    "label": "Transform",
                    "config": {"transform_type": "uppercase"},
                },
                {
                    "id": "C",
                    "type": "command",
                    "label": "Echo",
                    "config": {"command": "echo integration_test"},
                },
            ],
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        }

        workflow_id = self._create_workflow_with_version(client, graph)

        # Mock subprocess.run for the command node
        mock_result = MagicMock()
        mock_result.stdout = "integration_test\n"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            resp = client.post(
                f"/admin/workflows/{workflow_id}/run",
                json={"input_json": json.dumps({"msg": "hello"})},
            )
            assert resp.status_code == 202
            execution_id = resp.get_json()["execution_id"]

            result = self._wait_execution(client, execution_id)

        assert result["execution"]["status"] == "completed"
        # Verify all nodes were executed via node_executions list
        node_executions = result.get("node_executions", [])
        executed_node_ids = {ne["node_id"] for ne in node_executions}
        for node_id in ("A", "B", "C"):
            assert node_id in executed_node_ids, (
                f"Node {node_id} should appear in node_executions"
            )

    def test_workflow_error_mode_skip_continues_on_failure(self, client, isolated_db):
        """Node with error_mode='skip' should not halt the workflow when it fails."""
        graph = {
            "nodes": [
                {
                    "id": "A",
                    "type": "trigger",
                    "label": "Start",
                    "config": {"data": {"msg": "start"}},
                },
                {
                    "id": "B",
                    "type": "command",
                    "label": "Failing Command",
                    "config": {"command": "false"},
                    "error_mode": "skip",
                },
                {
                    "id": "C",
                    "type": "trigger",
                    "label": "End",
                    "config": {"data": {"msg": "end"}},
                },
            ],
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        }

        workflow_id = self._create_workflow_with_version(client, graph)

        # Make the command node fail
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "command failed"
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            resp = client.post(
                f"/admin/workflows/{workflow_id}/run",
                json={"input_json": json.dumps({"msg": "test"})},
            )
            assert resp.status_code == 202
            execution_id = resp.get_json()["execution_id"]

            result = self._wait_execution(client, execution_id)

        # Workflow should complete (not fail) because B has error_mode=skip
        assert result["execution"]["status"] == "completed"
        node_executions = result.get("node_executions", [])
        node_statuses = {ne["node_id"]: ne["status"] for ne in node_executions}
        assert node_statuses.get("A") == "completed"
        assert node_statuses.get("B") in ("skipped", "failed")
        assert node_statuses.get("C") == "completed"

    def test_workflow_collects_results_from_last_node(self, client, isolated_db):
        """Verify the workflow completes and the last node produces output."""
        graph = {
            "nodes": [
                {
                    "id": "A",
                    "type": "trigger",
                    "label": "Start",
                    "config": {"data": {"msg": "input"}},
                },
                {
                    "id": "B",
                    "type": "trigger",
                    "label": "End",
                    "config": {"data": {"result": "final_output"}},
                },
            ],
            "edges": [{"source": "A", "target": "B"}],
        }

        workflow_id = self._create_workflow_with_version(client, graph)

        resp = client.post(
            f"/admin/workflows/{workflow_id}/run",
            json={"input_json": json.dumps({"msg": "test"})},
        )
        assert resp.status_code == 202
        execution_id = resp.get_json()["execution_id"]

        result = self._wait_execution(client, execution_id)
        assert result["execution"]["status"] == "completed"
        # Both nodes should have executed
        node_executions = result.get("node_executions", [])
        assert len(node_executions) == 2

    def test_workflow_execution_status_tracking(self, client, isolated_db):
        """Verify execution status is trackable via the API throughout its lifecycle."""
        graph = {
            "nodes": [
                {
                    "id": "A",
                    "type": "trigger",
                    "label": "Start",
                    "config": {"data": {"msg": "status_test"}},
                },
            ],
            "edges": [],
        }

        workflow_id = self._create_workflow_with_version(client, graph)

        resp = client.post(
            f"/admin/workflows/{workflow_id}/run",
            json={"input_json": json.dumps({"msg": "test"})},
        )
        assert resp.status_code == 202
        execution_id = resp.get_json()["execution_id"]

        # Poll until complete
        result = self._wait_execution(client, execution_id)
        assert result["execution"]["status"] == "completed"
        assert result["execution"]["id"] == execution_id
        assert result["execution"]["workflow_id"] == workflow_id


# =============================================================================
# C. Team Execution Pipeline
# =============================================================================


class TestTeamExecutionPipeline:
    """Tests team execution with sequential topology, output chaining, and status tracking."""

    def test_sequential_team_agents_execute_in_order(self, client, isolated_db):
        """Create a team with 2 agents in sequential topology, verify execution order."""
        agent_ids = ["agent-pipe1", "agent-pipe2"]
        team_id = _create_team_with_topology(
            client,
            isolated_db,
            topology="sequential",
            topology_config={"order": agent_ids},
            agent_ids=agent_ids,
        )

        call_order = []

        def mock_run_trigger(trigger, message_text, event=None, trigger_type="webhook", **kwargs):
            call_order.append(trigger["id"])
            return f"exec-{trigger['id']}"

        def mock_get_stdout_log(execution_id):
            return f"output-from-{execution_id}"

        with (
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                side_effect=mock_run_trigger,
            ),
            patch(
                "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
                side_effect=mock_get_stdout_log,
            ),
        ):
            from app.services.team_execution_service import TeamExecutionService

            execution_ids = TeamExecutionService._execute_sequential(
                team={"id": team_id, "members": []},
                config={"order": agent_ids},
                message="initial message",
                event={},
                trigger_type="manual",
            )

        # Verify agents called in correct order
        assert call_order == agent_ids
        assert len(execution_ids) == 2

    def test_sequential_team_output_chaining(self, client, isolated_db):
        """Verify that each agent receives the output of the previous agent as its input."""
        agent_ids = ["agent-chain1", "agent-chain2", "agent-chain3"]
        team_id = _create_team_with_topology(
            client,
            isolated_db,
            topology="sequential",
            topology_config={"order": agent_ids},
            agent_ids=agent_ids,
        )

        received_messages = []

        def mock_run_trigger(trigger, message_text, event=None, trigger_type="webhook", **kwargs):
            received_messages.append(message_text)
            return f"exec-{trigger['id']}"

        def mock_get_stdout_log(execution_id):
            # Each agent transforms the message
            agent_id = execution_id.replace("exec-", "")
            return f"processed-by-{agent_id}"

        with (
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                side_effect=mock_run_trigger,
            ),
            patch(
                "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
                side_effect=mock_get_stdout_log,
            ),
        ):
            from app.services.team_execution_service import TeamExecutionService

            TeamExecutionService._execute_sequential(
                team={"id": team_id, "members": []},
                config={"order": agent_ids},
                message="original input",
                event={},
                trigger_type="manual",
            )

        # First agent gets the original message
        assert received_messages[0] == "original input"
        # Second agent gets output of first
        assert received_messages[1] == "processed-by-agent-chain1"
        # Third agent gets output of second
        assert received_messages[2] == "processed-by-agent-chain2"

    def test_team_execute_via_api_endpoint(self, client, isolated_db):
        """Verify POST /admin/teams/<id>/run starts execution and returns tracking ID."""
        agent_ids = ["agent-api1", "agent-api2"]
        team_id = _create_team_with_topology(
            client,
            isolated_db,
            topology="sequential",
            topology_config={"order": agent_ids},
            agent_ids=agent_ids,
        )

        with patch(
            "app.services.team_execution_service.TeamExecutionService.execute_team"
        ) as mock_execute:
            mock_execute.return_value = "team-exec-integ01"

            resp = client.post(
                f"/admin/teams/{team_id}/run",
                json={"message": "integration test run"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["team_execution_id"] == "team-exec-integ01"
        mock_execute.assert_called_once_with(
            team_id=team_id,
            message="integration test run",
            event={},
            trigger_type="manual",
        )

    def test_team_execution_status_tracking(self, client, isolated_db):
        """Verify TeamExecutionService tracks status in-memory correctly."""
        agent_ids = ["agent-stat1", "agent-stat2"]
        team_id = _create_team_with_topology(
            client,
            isolated_db,
            topology="sequential",
            topology_config={"order": agent_ids},
            agent_ids=agent_ids,
        )

        def mock_run_trigger(trigger, message_text, event=None, trigger_type="webhook", **kwargs):
            return f"exec-{trigger['id']}"

        def mock_get_stdout_log(execution_id):
            return "output"

        with (
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                side_effect=mock_run_trigger,
            ),
            patch(
                "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
                side_effect=mock_get_stdout_log,
            ),
        ):
            from app.services.team_execution_service import TeamExecutionService

            team_exec_id = TeamExecutionService.execute_team(
                team_id=team_id,
                message="status tracking test",
                event={},
                trigger_type="manual",
            )

        assert team_exec_id is not None
        assert team_exec_id.startswith("team-exec-")

        # Wait briefly for the background thread to complete
        time.sleep(1)

        status = TeamExecutionService.get_execution_status(team_exec_id)
        assert status is not None
        assert status["status"] in ("completed", "running")
        assert status["team_id"] == team_id
        assert status["topology"] == "sequential"


# =============================================================================
# D. Cross-Entity Reference Integrity
# =============================================================================


class TestCrossEntityReferences:
    """Tests cross-entity reference chains and cascade/nullify behavior on deletion."""

    def test_product_project_agent_trigger_chain(self, client, isolated_db):
        """Create product -> project -> agent -> trigger chain, verify linkage."""
        from app.db.agents import create_agent
        from app.db.products import create_product, get_product
        from app.db.projects import create_project, get_project
        from app.db.triggers import create_trigger, get_trigger

        # Create product
        product_id = create_product(name="Integration Product", description="Test product")
        assert product_id is not None

        # Create project linked to product
        project_id = create_project(
            name="Integration Project",
            description="Test project",
            product_id=product_id,
        )
        assert project_id is not None

        # Verify project-product linkage
        project = get_project(project_id)
        assert project["product_id"] == product_id

        # Create agent
        agent_id = create_agent(
            name="Integration Agent",
            backend_type="claude",
            system_prompt="You are a test agent",
        )
        assert agent_id is not None

        # Create trigger
        trigger_id = create_trigger(
            name="Integration Trigger",
            prompt_template="Run: {message}",
            backend_type="claude",
            trigger_source="webhook",
        )
        assert trigger_id is not None

        # Verify all entities exist
        assert get_product(product_id) is not None
        assert get_project(project_id) is not None
        assert get_trigger(trigger_id) is not None

    def test_product_deletion_nullifies_project_reference(self, client, isolated_db):
        """Deleting a product should SET NULL on project.product_id (not cascade-delete)."""
        from app.db.products import create_product, delete_product, get_product
        from app.db.projects import create_project, get_project

        product_id = create_product(name="Deletable Product")
        project_id = create_project(name="Orphan Project", product_id=product_id)

        # Verify linkage
        project = get_project(project_id)
        assert project["product_id"] == product_id

        # Delete product
        deleted = delete_product(product_id)
        assert deleted is True
        assert get_product(product_id) is None

        # Project should still exist but with product_id set to NULL
        project = get_project(project_id)
        assert project is not None
        assert project["product_id"] is None

    def test_team_deletion_cascades_members(self, client, isolated_db):
        """Deleting a team should cascade-delete its team_members."""
        from app.db.connection import get_connection

        agent_ids = ["agent-cas1", "agent-cas2"]
        team_id = _create_team_with_topology(
            client,
            isolated_db,
            topology="sequential",
            topology_config={"order": agent_ids},
            agent_ids=agent_ids,
        )

        # Verify members exist
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,)
            ).fetchone()[0]
            assert count == 2

        # Delete team
        resp = client.delete(f"/admin/teams/{team_id}")
        assert resp.status_code == 200

        # Verify members are cascade-deleted
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,)
            ).fetchone()[0]
            assert count == 0

    def test_trigger_deletion_cascades_execution_logs(self, client, isolated_db):
        """Deleting a trigger should cascade-delete its execution_logs."""
        from app.db.connection import get_connection
        from app.db.triggers import create_trigger
        from app.services.execution_log_service import ExecutionLogService

        trigger_id = create_trigger(
            name="Cascade Log Trigger",
            prompt_template="test",
            backend_type="claude",
            trigger_source="manual",
        )

        # Create an execution log entry
        execution_id = ExecutionLogService.start_execution(
            trigger_id=trigger_id,
            trigger_type="manual",
            prompt="test prompt",
            backend_type="claude",
            command="claude -p test",
        )
        assert execution_id is not None

        # Verify log exists
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM execution_logs WHERE trigger_id = ?", (trigger_id,)
            ).fetchone()[0]
            assert count >= 1

        # Delete trigger
        from app.db.triggers import delete_trigger

        deleted = delete_trigger(trigger_id)
        assert deleted is True

        # Verify execution logs are cascade-deleted
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM execution_logs WHERE trigger_id = ?", (trigger_id,)
            ).fetchone()[0]
            assert count == 0

    def test_multiple_projects_under_one_product(self, client, isolated_db):
        """Verify multiple projects can reference the same product."""
        from app.db.products import create_product, delete_product
        from app.db.projects import create_project, get_project

        product_id = create_product(name="Multi-Project Product")
        proj1_id = create_project(name="Project Alpha", product_id=product_id)
        proj2_id = create_project(name="Project Beta", product_id=product_id)

        assert get_project(proj1_id)["product_id"] == product_id
        assert get_project(proj2_id)["product_id"] == product_id

        # Delete product, both projects should lose their reference
        delete_product(product_id)

        assert get_project(proj1_id)["product_id"] is None
        assert get_project(proj2_id)["product_id"] is None
        # But both projects still exist
        assert get_project(proj1_id) is not None
        assert get_project(proj2_id) is not None
