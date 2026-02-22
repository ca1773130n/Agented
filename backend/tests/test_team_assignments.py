"""Tests for team agent assignment CRUD, topology validation, and trigger config."""

import json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_team(client, name="Test Team", **kwargs):
    """Create a team and return its ID."""
    payload = {"name": name, **kwargs}
    resp = client.post("/admin/teams/", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["team"]["id"]


def _create_agent(isolated_db):
    """Create a minimal agent directly in the DB. Returns agent_id."""
    from app.database import _get_unique_agent_id, get_connection

    with get_connection() as conn:
        agent_id = _get_unique_agent_id(conn)
        conn.execute(
            "INSERT INTO agents (id, name, backend_type) VALUES (?, ?, ?)",
            (agent_id, "Test Agent", "claude"),
        )
        conn.commit()
    return agent_id


def _create_agent_with_id(isolated_db, agent_id, name="Test Agent"):
    """Create an agent with a specific ID."""
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, backend_type) VALUES (?, ?, ?)",
            (agent_id, name, "claude"),
        )
        conn.commit()
    return agent_id


def _add_member(client, team_id, agent_id):
    """Add an agent as a team member. Returns member_id."""
    resp = client.post(
        f"/admin/teams/{team_id}/members",
        json={"agent_id": agent_id},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["member"]["id"]


# ---------------------------------------------------------------------------
# Test 1: Add assignment
# ---------------------------------------------------------------------------


def test_add_assignment(client, isolated_db):
    """Create team, add agent member, add skill assignment, verify 201 response."""
    agent_id = _create_agent(isolated_db)
    team_id = _create_team(client)
    _add_member(client, team_id, agent_id)

    resp = client.post(
        f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
        json={
            "entity_type": "skill",
            "entity_id": "code-review",
            "entity_name": "Code Review",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["message"] == "Assignment added"
    assignment = data["assignment"]
    assert assignment["team_id"] == team_id
    assert assignment["agent_id"] == agent_id
    assert assignment["entity_type"] == "skill"
    assert assignment["entity_id"] == "code-review"
    assert assignment["entity_name"] == "Code Review"


# ---------------------------------------------------------------------------
# Test 2: List assignments
# ---------------------------------------------------------------------------


def test_list_assignments(client, isolated_db):
    """Add multiple assignments, verify list endpoint returns all."""
    agent_id = _create_agent(isolated_db)
    team_id = _create_team(client)
    _add_member(client, team_id, agent_id)

    # Add two assignments
    client.post(
        f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
        json={"entity_type": "skill", "entity_id": "review"},
    )
    client.post(
        f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
        json={"entity_type": "command", "entity_id": "deploy"},
    )

    # List for agent
    resp = client.get(f"/admin/teams/{team_id}/agents/{agent_id}/assignments")
    assert resp.status_code == 200
    assignments = resp.get_json()["assignments"]
    assert len(assignments) == 2

    # List for team
    resp = client.get(f"/admin/teams/{team_id}/assignments")
    assert resp.status_code == 200
    assert len(resp.get_json()["assignments"]) == 2


# ---------------------------------------------------------------------------
# Test 3: Delete assignment
# ---------------------------------------------------------------------------


def test_delete_assignment(client, isolated_db):
    """Add assignment, delete it, verify it's gone."""
    agent_id = _create_agent(isolated_db)
    team_id = _create_team(client)
    _add_member(client, team_id, agent_id)

    resp = client.post(
        f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
        json={"entity_type": "hook", "entity_id": "pre-commit"},
    )
    assignment_id = resp.get_json()["assignment"]["id"]

    # Delete
    resp = client.delete(f"/admin/teams/{team_id}/assignments/{assignment_id}")
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "Assignment deleted"

    # Verify gone
    resp = client.get(f"/admin/teams/{team_id}/assignments")
    assert len(resp.get_json()["assignments"]) == 0


# ---------------------------------------------------------------------------
# Test 4: Assignment requires team membership
# ---------------------------------------------------------------------------


def test_assignment_requires_team_membership(client, isolated_db):
    """Try to add assignment for agent not in team, expect 400."""
    agent_id = _create_agent(isolated_db)
    team_id = _create_team(client)
    # Do NOT add agent as member

    resp = client.post(
        f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
        json={"entity_type": "skill", "entity_id": "test-skill"},
    )
    assert resp.status_code == 400
    assert "not a member" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# Test 5: Topology update valid
# ---------------------------------------------------------------------------


def test_topology_update_valid(client, isolated_db):
    """Set sequential topology with valid config, verify stored."""
    agent1 = _create_agent_with_id(isolated_db, "agent-aaa001", "Agent A")
    agent2 = _create_agent_with_id(isolated_db, "agent-bbb002", "Agent B")
    team_id = _create_team(client)
    _add_member(client, team_id, agent1)
    _add_member(client, team_id, agent2)

    config = {"order": [agent1, agent2]}
    resp = client.put(
        f"/admin/teams/{team_id}/topology",
        json={"topology": "sequential", "topology_config": config},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["topology"] == "sequential"
    # topology_config is stored as JSON string
    stored_config = json.loads(data["topology_config"])
    assert stored_config["order"] == [agent1, agent2]


# ---------------------------------------------------------------------------
# Test 6: Topology validation rejects invalid
# ---------------------------------------------------------------------------


def test_topology_validation_rejects_invalid(client, isolated_db):
    """Set generator_critic with same agent as both roles, expect 400."""
    agent_id = _create_agent_with_id(isolated_db, "agent-ccc003", "Agent C")
    team_id = _create_team(client)
    _add_member(client, team_id, agent_id)

    resp = client.put(
        f"/admin/teams/{team_id}/topology",
        json={
            "topology": "generator_critic",
            "topology_config": {"generator": agent_id, "critic": agent_id},
        },
    )
    assert resp.status_code == 400
    assert "differ" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# Test 7: Trigger update
# ---------------------------------------------------------------------------


def test_trigger_update(client, isolated_db):
    """Set webhook trigger config, verify stored."""
    team_id = _create_team(client)

    trigger_cfg = {
        "match_field_path": "event.type",
        "match_field_value": "deployment",
    }
    resp = client.put(
        f"/admin/teams/{team_id}/trigger",
        json={
            "trigger_source": "webhook",
            "trigger_config": trigger_cfg,
            "enabled": 1,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["trigger_source"] == "webhook"
    stored = json.loads(data["trigger_config"])
    assert stored["match_field_path"] == "event.type"
    assert data["enabled"] == 1


# ---------------------------------------------------------------------------
# Test 8: Manual run placeholder
# ---------------------------------------------------------------------------


def test_manual_run_endpoint(client, isolated_db):
    """POST to run endpoint -- team without topology returns 400."""
    team_id = _create_team(client)

    resp = client.post(f"/admin/teams/{team_id}/run")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "no topology" in data["error"].lower()


# ---------------------------------------------------------------------------
# Test 9: Bulk delete assignments
# ---------------------------------------------------------------------------


def test_bulk_delete_assignments(client, isolated_db):
    """Bulk delete assignments for an agent in a team."""
    agent_id = _create_agent(isolated_db)
    team_id = _create_team(client)
    _add_member(client, team_id, agent_id)

    # Add multiple assignments
    for etype in ["skill", "command", "hook"]:
        client.post(
            f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
            json={"entity_type": etype, "entity_id": f"test-{etype}"},
        )

    # Bulk delete
    resp = client.delete(f"/admin/teams/{team_id}/agents/{agent_id}/assignments")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["deleted_count"] == 3

    # Verify empty
    resp = client.get(f"/admin/teams/{team_id}/assignments")
    assert len(resp.get_json()["assignments"]) == 0


# ---------------------------------------------------------------------------
# Test 10: Invalid topology type rejected
# ---------------------------------------------------------------------------


def test_invalid_topology_type_rejected(client, isolated_db):
    """Set invalid topology type, expect 400."""
    team_id = _create_team(client)

    resp = client.put(
        f"/admin/teams/{team_id}/topology",
        json={"topology": "nonexistent"},
    )
    assert resp.status_code == 400
    assert "Invalid topology" in resp.get_json()["error"]
