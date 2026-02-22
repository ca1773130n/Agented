"""Tests for team execution service, dispatch wiring, and manual run endpoint."""

import threading
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_agent_in_db(isolated_db, agent_id, name="Test Agent", backend_type="claude"):
    """Create an agent directly in the DB."""
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, backend_type, enabled) VALUES (?, ?, ?, 1)",
            (agent_id, name, backend_type),
        )
        conn.commit()


def _create_team_with_topology(
    client, isolated_db, topology, topology_config, agent_ids, trigger_source="manual"
):
    """Create a team with agents, members, and topology config. Returns team_id."""
    # Create agents
    for aid in agent_ids:
        _create_agent_in_db(isolated_db, aid, name=f"Agent {aid}")

    # Create team
    resp = client.post("/admin/teams/", json={"name": "Test Team"})
    assert resp.status_code == 201
    team_id = resp.get_json()["team"]["id"]

    # Add members
    for aid in agent_ids:
        resp = client.post(
            f"/admin/teams/{team_id}/members",
            json={"agent_id": aid, "name": f"Agent {aid}"},
        )
        assert resp.status_code == 201

    # Set topology
    resp = client.put(
        f"/admin/teams/{team_id}/topology",
        json={"topology": topology, "topology_config": topology_config},
    )
    assert resp.status_code == 200

    # Set trigger and enable
    resp = client.put(
        f"/admin/teams/{team_id}/trigger",
        json={"trigger_source": trigger_source, "enabled": 1},
    )
    assert resp.status_code == 200

    return team_id


# ---------------------------------------------------------------------------
# Test 1: Import check
# ---------------------------------------------------------------------------


def test_team_execution_service_import():
    """Verify TeamExecutionService imports without errors."""
    from app.services.team_execution_service import TeamExecutionService

    assert hasattr(TeamExecutionService, "execute_team")
    assert hasattr(TeamExecutionService, "_execute_sequential")
    assert hasattr(TeamExecutionService, "_execute_parallel")
    assert hasattr(TeamExecutionService, "_execute_coordinator")
    assert hasattr(TeamExecutionService, "_execute_generator_critic")


# ---------------------------------------------------------------------------
# Test 2: Sequential execution order
# ---------------------------------------------------------------------------


def test_sequential_execution_builds_correct_flow(client, isolated_db):
    """Create a team with sequential topology, verify agents are called in order."""
    agent_ids = ["agent-seq1", "agent-seq2", "agent-seq3"]
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
        # Return distinct output for each agent to verify chaining
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
            message="test message",
            event={},
            trigger_type="manual",
        )

    # Verify order
    assert call_order == agent_ids
    assert len(execution_ids) == 3


# ---------------------------------------------------------------------------
# Test 3: Parallel execution spawns all agents
# ---------------------------------------------------------------------------


def test_parallel_execution_spawns_threads(client, isolated_db):
    """Create team with parallel topology, verify all agents are called."""
    agent_ids = ["agent-par1", "agent-par2", "agent-par3"]
    team_id = _create_team_with_topology(
        client,
        isolated_db,
        topology="parallel",
        topology_config={"agents": agent_ids},
        agent_ids=agent_ids,
    )

    called_agents = []
    call_lock = threading.Lock()

    def mock_run_trigger(trigger, message_text, event=None, trigger_type="webhook", **kwargs):
        with call_lock:
            called_agents.append(trigger["id"])
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

        execution_ids = TeamExecutionService._execute_parallel(
            team={"id": team_id, "members": []},
            config={"agents": agent_ids},
            message="test message",
            event={},
            trigger_type="manual",
        )

    # Verify all agents were called (order doesn't matter)
    assert sorted(called_agents) == sorted(agent_ids)
    assert len(execution_ids) == 3


# ---------------------------------------------------------------------------
# Test 4: Webhook dispatch includes teams
# ---------------------------------------------------------------------------


def test_webhook_dispatch_includes_teams(client, isolated_db):
    """Verify dispatch_webhook_event triggers matching teams."""
    agent_ids = ["agent-wh1", "agent-wh2"]
    team_id = _create_team_with_topology(
        client,
        isolated_db,
        topology="parallel",
        topology_config={"agents": agent_ids},
        agent_ids=agent_ids,
        trigger_source="webhook",
    )

    # Set trigger_config with match criteria
    client.put(
        f"/admin/teams/{team_id}/trigger",
        json={
            "trigger_source": "webhook",
            "trigger_config": {
                "text_field_path": "message",
            },
            "enabled": 1,
        },
    )

    with patch(
        "app.services.team_execution_service.TeamExecutionService.execute_team"
    ) as mock_execute:
        mock_execute.return_value = "team-exec-test123"

        from app.services.execution_service import ExecutionService

        triggered = ExecutionService.dispatch_webhook_event({"message": "hello world"})

    assert triggered is True
    mock_execute.assert_called_once()
    call_args = mock_execute.call_args
    assert call_args[0][0] == team_id  # team_id
    assert call_args[0][1] == "hello world"  # text
    assert call_args[0][3] == "webhook"  # trigger_type


# ---------------------------------------------------------------------------
# Test 5: Manual run endpoint
# ---------------------------------------------------------------------------


def test_manual_run_endpoint(client, isolated_db):
    """POST to /admin/teams/<id>/run returns 200 with execution tracking ID."""
    agent_ids = ["agent-mr1", "agent-mr2"]
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
        mock_execute.return_value = "team-exec-abcd1234"

        resp = client.post(
            f"/admin/teams/{team_id}/run",
            json={"message": "run this team"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "Team execution started"
    assert data["team_execution_id"] == "team-exec-abcd1234"
    mock_execute.assert_called_once_with(
        team_id=team_id,
        message="run this team",
        event={},
        trigger_type="manual",
    )


# ---------------------------------------------------------------------------
# Test 6: Generator-critic stops on approval
# ---------------------------------------------------------------------------


def test_generator_critic_stops_on_approval(client, isolated_db):
    """Mock execution to return APPROVED from critic on first iteration."""
    agent_ids = ["agent-gen1", "agent-crit1"]
    team_id = _create_team_with_topology(
        client,
        isolated_db,
        topology="generator_critic",
        topology_config={
            "generator": "agent-gen1",
            "critic": "agent-crit1",
            "max_iterations": 3,
        },
        agent_ids=agent_ids,
    )

    call_count = [0]

    def mock_run_trigger(trigger, message_text, event=None, trigger_type="webhook", **kwargs):
        call_count[0] += 1
        return f"exec-{call_count[0]}"

    def mock_get_stdout_log(execution_id):
        # Generator returns content, critic always approves
        if "1" in execution_id:
            return "Generated content here"
        return "APPROVED: looks good"

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

        execution_ids = TeamExecutionService._execute_generator_critic(
            team={"id": team_id, "members": []},
            config={
                "generator": "agent-gen1",
                "critic": "agent-crit1",
                "max_iterations": 3,
            },
            message="write something",
            event={},
            trigger_type="manual",
        )

    # Should have exactly 2 executions: 1 generator + 1 critic
    assert len(execution_ids) == 2
    # Should have stopped after 1 iteration (critic approved)
    assert call_count[0] == 2
