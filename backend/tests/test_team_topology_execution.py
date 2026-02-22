"""Tests for new topology execution strategies (hierarchical, human-in-loop, composite)
and validation rules for all three new patterns."""

import json
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


def _create_team_with_members(isolated_db, agent_ids, topology=None, topology_config=None):
    """Create a team with agents and members directly in the DB.

    Sets topology directly without API validation (needed for hierarchical
    which requires edges to exist, and for invalid-config tests).
    Returns (team_id, member_ids dict).
    """
    from app.database import add_team, add_team_member, update_team

    # Create agents
    for aid in agent_ids:
        _create_agent_in_db(isolated_db, aid, name=f"Agent {aid}")

    # Create team
    team_id = add_team(name="Test Team")
    assert team_id is not None

    # Add members and track member_ids
    member_ids = {}  # agent_id -> member_id (int)
    for aid in agent_ids:
        mid = add_team_member(team_id, name=f"Agent {aid}", agent_id=aid)
        assert mid is not None
        member_ids[aid] = mid

    # Set topology directly in DB (bypasses validation)
    if topology:
        config_str = json.dumps(topology_config) if topology_config else None
        update_team(team_id, topology=topology, topology_config=config_str, enabled=1)

    return team_id, member_ids


def _add_team_edge_in_db(isolated_db, team_id, source_member_id, target_member_id, edge_type):
    """Insert a directed edge directly into the team_edges table."""
    from app.database import get_connection

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO team_edges (team_id, source_member_id, target_member_id, edge_type)
               VALUES (?, ?, ?, ?)""",
            (team_id, source_member_id, target_member_id, edge_type),
        )
        conn.commit()
        return cursor.lastrowid


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_run_trigger_factory(call_order=None):
    """Create a mock run_trigger that records call order and returns execution IDs."""
    if call_order is None:
        call_order = []

    def mock_run_trigger(trigger, message_text, event=None, trigger_type="webhook", **kwargs):
        call_order.append(trigger["id"])
        return f"exec-{trigger['id']}"

    return mock_run_trigger, call_order


def _mock_get_stdout_log(execution_id):
    """Return distinct output for each execution for chaining verification."""
    return f"output-from-{execution_id}"


# ---------------------------------------------------------------------------
# Test 1: Hierarchical execution order
# ---------------------------------------------------------------------------


def test_hierarchical_execution_order(isolated_db):
    """Create team with 3 agents (A lead, B and C delegates). Verify A runs first."""
    agent_ids = ["agent-ha", "agent-hb", "agent-hc"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="hierarchical",
        topology_config={"lead": "agent-ha"},
    )

    # Add delegation edges: A -> B, A -> C
    _add_team_edge_in_db(
        isolated_db, team_id, member_ids["agent-ha"], member_ids["agent-hb"], "delegation"
    )
    _add_team_edge_in_db(
        isolated_db, team_id, member_ids["agent-ha"], member_ids["agent-hc"], "delegation"
    )

    mock_run, call_order = _mock_run_trigger_factory()

    # Build members list matching get_team_detail format
    members = [
        {"id": member_ids[aid], "agent_id": aid, "super_agent_id": None, "name": f"Agent {aid}"}
        for aid in agent_ids
    ]

    with (
        patch(
            "app.services.execution_service.ExecutionService.run_trigger",
            side_effect=mock_run,
        ),
        patch(
            "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
            side_effect=_mock_get_stdout_log,
        ),
    ):
        from app.services.team_execution_service import TeamExecutionService

        execution_ids = TeamExecutionService._execute_hierarchical(
            team={"id": team_id, "members": members},
            config={"lead": "agent-ha"},
            message="test message",
            event={},
            trigger_type="manual",
        )

    # A runs first (lead), then B and C (delegates in order)
    assert call_order[0] == "agent-ha"
    assert set(call_order[1:]) == {"agent-hb", "agent-hc"}
    assert len(execution_ids) == 3


# ---------------------------------------------------------------------------
# Test 2: Hierarchical no edges returns just lead execution
# ---------------------------------------------------------------------------


def test_hierarchical_no_edges_returns_lead_only(isolated_db):
    """Team with hierarchical topology but no edges. Lead still runs."""
    agent_ids = ["agent-lone"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="hierarchical",
        topology_config={"lead": "agent-lone"},
    )

    mock_run, call_order = _mock_run_trigger_factory()
    members = [
        {
            "id": member_ids["agent-lone"],
            "agent_id": "agent-lone",
            "super_agent_id": None,
            "name": "Agent agent-lone",
        }
    ]

    with (
        patch(
            "app.services.execution_service.ExecutionService.run_trigger",
            side_effect=mock_run,
        ),
        patch(
            "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
            side_effect=_mock_get_stdout_log,
        ),
    ):
        from app.services.team_execution_service import TeamExecutionService

        execution_ids = TeamExecutionService._execute_hierarchical(
            team={"id": team_id, "members": members},
            config={"lead": "agent-lone"},
            message="test message",
            event={},
            trigger_type="manual",
        )

    # Only lead runs, no delegates
    assert call_order == ["agent-lone"]
    assert len(execution_ids) == 1


# ---------------------------------------------------------------------------
# Test 3: Human-in-loop approval continues execution
# ---------------------------------------------------------------------------


def test_human_in_loop_approval_continues(isolated_db):
    """Start execution with approval gate, approve immediately, verify both agents execute."""
    agent_ids = ["agent-hil1", "agent-hil2"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="human_in_loop",
        topology_config={"order": agent_ids, "approval_nodes": ["agent-hil2"]},
    )

    mock_run, call_order = _mock_run_trigger_factory()

    from app.services.team_execution_service import TeamExecutionService

    # Set up a fake execution entry so _find_exec_id_for_team works
    test_exec_id = "team-exec-hiltest1"
    with TeamExecutionService._lock:
        TeamExecutionService._executions[test_exec_id] = {
            "team_id": team_id,
            "topology": "human_in_loop",
            "trigger_type": "manual",
            "status": "running",
            "execution_ids": [],
        }

    # Start a thread that will approve after a short delay
    def approve_after_delay():
        import time

        time.sleep(0.1)
        TeamExecutionService.approve_execution(test_exec_id)

    approver = threading.Thread(target=approve_after_delay, daemon=True)
    approver.start()

    with (
        patch(
            "app.services.execution_service.ExecutionService.run_trigger",
            side_effect=mock_run,
        ),
        patch(
            "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
            side_effect=_mock_get_stdout_log,
        ),
    ):
        execution_ids = TeamExecutionService._execute_human_in_loop(
            team={"id": team_id, "members": []},
            config={
                "order": agent_ids,
                "approval_nodes": ["agent-hil2"],
                "approval_timeout": 5,
            },
            message="test message",
            event={},
            trigger_type="manual",
        )

    approver.join(timeout=2)

    # Both agents should have executed
    assert len(execution_ids) == 2
    assert call_order == ["agent-hil1", "agent-hil2"]

    # Clean up
    with TeamExecutionService._lock:
        TeamExecutionService._executions.pop(test_exec_id, None)


# ---------------------------------------------------------------------------
# Test 4: Human-in-loop timeout stops execution
# ---------------------------------------------------------------------------


def test_human_in_loop_timeout_stops(isolated_db):
    """Approval gate with very short timeout. Do NOT approve. Verify stops."""
    agent_ids = ["agent-to1", "agent-to2"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="human_in_loop",
        topology_config={"order": agent_ids, "approval_nodes": ["agent-to2"]},
    )

    mock_run, call_order = _mock_run_trigger_factory()

    from app.services.team_execution_service import TeamExecutionService

    # Set up a fake execution entry
    test_exec_id = "team-exec-timeout1"
    with TeamExecutionService._lock:
        TeamExecutionService._executions[test_exec_id] = {
            "team_id": team_id,
            "topology": "human_in_loop",
            "trigger_type": "manual",
            "status": "running",
            "execution_ids": [],
        }

    with (
        patch(
            "app.services.execution_service.ExecutionService.run_trigger",
            side_effect=mock_run,
        ),
        patch(
            "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
            side_effect=_mock_get_stdout_log,
        ),
    ):
        execution_ids = TeamExecutionService._execute_human_in_loop(
            team={"id": team_id, "members": []},
            config={
                "order": agent_ids,
                "approval_nodes": ["agent-to2"],
                "approval_timeout": 0.1,  # Very short timeout
            },
            message="test message",
            event={},
            trigger_type="manual",
        )

    # Only agent-to1 should have executed (before the approval gate)
    assert len(execution_ids) == 1
    assert call_order == ["agent-to1"]

    # Status should be approval_timeout
    with TeamExecutionService._lock:
        entry = TeamExecutionService._executions.get(test_exec_id)
        assert entry is not None
        assert entry["status"] == "approval_timeout"

    # Clean up
    with TeamExecutionService._lock:
        TeamExecutionService._executions.pop(test_exec_id, None)


# ---------------------------------------------------------------------------
# Test 5: Composite sequential-then-parallel
# ---------------------------------------------------------------------------


def test_composite_sequential_then_parallel(isolated_db):
    """Composite: first sub_group sequential (A->B), second parallel (C,D)."""
    agent_ids = ["agent-ca", "agent-cb", "agent-cc", "agent-cd"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="composite",
        topology_config={
            "sub_groups": [
                {"topology": "sequential", "config": {"order": ["agent-ca", "agent-cb"]}},
                {"topology": "parallel", "config": {"agents": ["agent-cc", "agent-cd"]}},
            ]
        },
    )

    mock_run, call_order = _mock_run_trigger_factory()

    with (
        patch(
            "app.services.execution_service.ExecutionService.run_trigger",
            side_effect=mock_run,
        ),
        patch(
            "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
            side_effect=_mock_get_stdout_log,
        ),
    ):
        from app.services.team_execution_service import TeamExecutionService

        execution_ids = TeamExecutionService._execute_composite(
            team={"id": team_id, "members": []},
            config={
                "sub_groups": [
                    {"topology": "sequential", "config": {"order": ["agent-ca", "agent-cb"]}},
                    {"topology": "parallel", "config": {"agents": ["agent-cc", "agent-cd"]}},
                ]
            },
            message="test message",
            event={},
            trigger_type="manual",
        )

    # A and B run first (sequential), then C and D (parallel)
    assert call_order[:2] == ["agent-ca", "agent-cb"]
    assert set(call_order[2:]) == {"agent-cc", "agent-cd"}
    assert len(execution_ids) == 4


# ---------------------------------------------------------------------------
# Test 6: Composite rejects nested composite (validation)
# ---------------------------------------------------------------------------


def test_composite_rejects_nested_composite(isolated_db):
    """Validate composite config where a sub_group has topology='composite'."""
    agent_ids = ["agent-nest1"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="composite",
        topology_config={"sub_groups": []},
    )

    from app.services.team_service import TeamService

    error = TeamService.validate_topology_config(
        team_id,
        "composite",
        {
            "sub_groups": [
                {
                    "topology": "composite",
                    "config": {"sub_groups": []},
                }
            ]
        },
    )
    assert error is not None
    assert "composite" in error.lower()
    assert "nesting" in error.lower() or "max" in error.lower() or "cannot" in error.lower()


# ---------------------------------------------------------------------------
# Test 7: Validate hierarchical config valid
# ---------------------------------------------------------------------------


def test_validate_hierarchical_config_valid(isolated_db):
    """Valid hierarchical config with lead and delegation edges. Returns None."""
    agent_ids = ["agent-vh1", "agent-vh2"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="hierarchical",
        topology_config={"lead": "agent-vh1"},
    )

    # Add delegation edge from vh1 -> vh2
    _add_team_edge_in_db(
        isolated_db, team_id, member_ids["agent-vh1"], member_ids["agent-vh2"], "delegation"
    )

    from app.services.team_service import TeamService

    error = TeamService.validate_topology_config(team_id, "hierarchical", {"lead": "agent-vh1"})
    assert error is None


# ---------------------------------------------------------------------------
# Test 8: Validate hierarchical config missing lead
# ---------------------------------------------------------------------------


def test_validate_hierarchical_config_missing_lead(isolated_db):
    """Config without lead key. Returns error string."""
    agent_ids = ["agent-ml1"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="hierarchical",
        topology_config={"lead": "agent-ml1"},
    )

    from app.services.team_service import TeamService

    error = TeamService.validate_topology_config(team_id, "hierarchical", {})
    assert error is not None
    assert "lead" in error.lower()


# ---------------------------------------------------------------------------
# Test 9: Validate human_in_loop config valid
# ---------------------------------------------------------------------------


def test_validate_human_in_loop_config_valid(isolated_db):
    """Valid order + approval_nodes. Returns None."""
    agent_ids = ["agent-vhil1", "agent-vhil2"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="human_in_loop",
        topology_config={"order": agent_ids, "approval_nodes": ["agent-vhil2"]},
    )

    from app.services.team_service import TeamService

    error = TeamService.validate_topology_config(
        team_id,
        "human_in_loop",
        {"order": agent_ids, "approval_nodes": ["agent-vhil2"]},
    )
    assert error is None


# ---------------------------------------------------------------------------
# Test 10: Validate human_in_loop approval_node not in order
# ---------------------------------------------------------------------------


def test_validate_human_in_loop_approval_not_in_order(isolated_db):
    """Approval node not in order list. Returns error."""
    agent_ids = ["agent-norder1", "agent-norder2"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="human_in_loop",
        topology_config={"order": ["agent-norder1"], "approval_nodes": ["agent-norder2"]},
    )

    from app.services.team_service import TeamService

    error = TeamService.validate_topology_config(
        team_id,
        "human_in_loop",
        {"order": ["agent-norder1"], "approval_nodes": ["agent-norder2"]},
    )
    assert error is not None
    assert "not in the 'order' list" in error


# ---------------------------------------------------------------------------
# Test 11: Validate composite config valid
# ---------------------------------------------------------------------------


def test_validate_composite_config_valid(isolated_db):
    """Valid sub_groups config. Returns None."""
    agent_ids = ["agent-vc1", "agent-vc2"]
    team_id, member_ids = _create_team_with_members(
        isolated_db,
        agent_ids,
        topology="composite",
        topology_config={
            "sub_groups": [
                {"topology": "sequential", "config": {"order": agent_ids}},
                {"topology": "parallel", "config": {"agents": agent_ids}},
            ]
        },
    )

    from app.services.team_service import TeamService

    error = TeamService.validate_topology_config(
        team_id,
        "composite",
        {
            "sub_groups": [
                {"topology": "sequential", "config": {"order": agent_ids}},
                {"topology": "parallel", "config": {"agents": agent_ids}},
            ]
        },
    )
    assert error is None


# ---------------------------------------------------------------------------
# Test 12: Approve execution not found
# ---------------------------------------------------------------------------


def test_approve_execution_not_found():
    """Call approve_execution with invalid ID. Returns False."""
    from app.services.team_execution_service import TeamExecutionService

    result = TeamExecutionService.approve_execution("team-exec-nonexistent")
    assert result is False
