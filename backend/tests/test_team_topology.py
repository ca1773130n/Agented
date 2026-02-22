"""Tests for team topology extensions: edges, SuperAgent members, and new topology types."""

from app.db.teams import (
    add_team,
    add_team_edge,
    add_team_member,
    delete_team_edge,
    delete_team_edges_by_team,
    get_team_detail,
    get_team_edges,
    get_team_hierarchy,
    get_team_members,
)
from app.models.team import VALID_TOPOLOGIES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_agent_in_db(isolated_db, agent_id, name="Test Agent"):
    """Create an agent directly in the DB."""
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, backend_type, enabled) VALUES (?, ?, ?, 1)",
            (agent_id, name, "claude"),
        )
        conn.commit()


def _create_super_agent_in_db(isolated_db, sa_id, name="Test SuperAgent"):
    """Create a super_agent directly in the DB."""
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO super_agents (id, name, backend_type) VALUES (?, ?, ?)",
            (sa_id, name, "claude"),
        )
        conn.commit()


def _create_team_with_members(isolated_db, agent_ids):
    """Create a team and add agent members. Returns (team_id, member_ids_dict)."""
    team_id = add_team(name="Topology Test Team")
    assert team_id is not None

    member_ids = {}
    for aid in agent_ids:
        _create_agent_in_db(isolated_db, aid, name=f"Agent {aid}")
        mid = add_team_member(team_id=team_id, agent_id=aid)
        assert mid is not None
        member_ids[aid] = mid

    return team_id, member_ids


# ---------------------------------------------------------------------------
# Test 1: SuperAgent member support
# ---------------------------------------------------------------------------


def test_add_team_member_with_super_agent_id(isolated_db):
    """Create a super_agent in DB, add as team member, verify member_type is 'super_agent'."""
    _create_super_agent_in_db(isolated_db, "super-sa001", "Lead SA")
    team_id = add_team(name="SA Test Team")
    assert team_id is not None

    member_id = add_team_member(team_id=team_id, super_agent_id="super-sa001")
    assert member_id is not None

    members = get_team_members(team_id)
    assert len(members) == 1

    member = members[0]
    assert member["super_agent_id"] == "super-sa001"
    assert member["super_agent_name"] == "Lead SA"
    assert member["member_type"] == "super_agent"
    assert member["agent_id"] is None
    assert member["name"] == "Lead SA"


# ---------------------------------------------------------------------------
# Test 2: XOR validation
# ---------------------------------------------------------------------------


def test_add_team_member_xor_validation(isolated_db):
    """Attempt to add member with both agent_id AND super_agent_id, verify returns None."""
    _create_agent_in_db(isolated_db, "agent-xor01", "Agent XOR")
    _create_super_agent_in_db(isolated_db, "super-xor01", "SA XOR")
    team_id = add_team(name="XOR Test Team")
    assert team_id is not None

    result = add_team_member(
        team_id=team_id,
        agent_id="agent-xor01",
        super_agent_id="super-xor01",
    )
    assert result is None


# ---------------------------------------------------------------------------
# Test 3: Add edge
# ---------------------------------------------------------------------------


def test_add_team_edge(isolated_db):
    """Create team with 2 members, add a delegation edge, verify returned by get_team_edges."""
    team_id, member_ids = _create_team_with_members(isolated_db, ["agent-edg01", "agent-edg02"])
    m1 = member_ids["agent-edg01"]
    m2 = member_ids["agent-edg02"]

    edge_id = add_team_edge(team_id, m1, m2, edge_type="delegation", label="delegates to")
    assert edge_id is not None

    edges = get_team_edges(team_id)
    assert len(edges) == 1
    assert edges[0]["source_member_id"] == m1
    assert edges[0]["target_member_id"] == m2
    assert edges[0]["edge_type"] == "delegation"
    assert edges[0]["label"] == "delegates to"


# ---------------------------------------------------------------------------
# Test 4: Self-loop rejected
# ---------------------------------------------------------------------------


def test_add_team_edge_self_loop_rejected(isolated_db):
    """Attempt edge from member to itself, verify rejected."""
    team_id, member_ids = _create_team_with_members(isolated_db, ["agent-self01"])
    m1 = member_ids["agent-self01"]

    result = add_team_edge(team_id, m1, m1, edge_type="delegation")
    assert result is None


# ---------------------------------------------------------------------------
# Test 5: Duplicate edge rejected
# ---------------------------------------------------------------------------


def test_add_team_edge_duplicate_rejected(isolated_db):
    """Add same edge twice (same type), verify second returns None."""
    team_id, member_ids = _create_team_with_members(isolated_db, ["agent-dup01", "agent-dup02"])
    m1 = member_ids["agent-dup01"]
    m2 = member_ids["agent-dup02"]

    first = add_team_edge(team_id, m1, m2, edge_type="delegation")
    assert first is not None

    second = add_team_edge(team_id, m1, m2, edge_type="delegation")
    assert second is None


# ---------------------------------------------------------------------------
# Test 6: Delete edge
# ---------------------------------------------------------------------------


def test_delete_team_edge(isolated_db):
    """Add and delete an edge, verify deletion."""
    team_id, member_ids = _create_team_with_members(isolated_db, ["agent-del01", "agent-del02"])
    m1 = member_ids["agent-del01"]
    m2 = member_ids["agent-del02"]

    edge_id = add_team_edge(team_id, m1, m2)
    assert edge_id is not None

    assert delete_team_edge(edge_id) is True
    assert len(get_team_edges(team_id)) == 0


# ---------------------------------------------------------------------------
# Test 7: Bulk delete edges
# ---------------------------------------------------------------------------


def test_delete_team_edges_by_team(isolated_db):
    """Add multiple edges, bulk delete, verify count."""
    team_id, member_ids = _create_team_with_members(
        isolated_db, ["agent-bulk01", "agent-bulk02", "agent-bulk03"]
    )
    m1 = member_ids["agent-bulk01"]
    m2 = member_ids["agent-bulk02"]
    m3 = member_ids["agent-bulk03"]

    add_team_edge(team_id, m1, m2, edge_type="delegation")
    add_team_edge(team_id, m2, m3, edge_type="delegation")
    add_team_edge(team_id, m1, m3, edge_type="reporting")

    deleted_count = delete_team_edges_by_team(team_id)
    assert deleted_count == 3
    assert len(get_team_edges(team_id)) == 0


# ---------------------------------------------------------------------------
# Test 8: Hierarchy recursive CTE
# ---------------------------------------------------------------------------


def test_get_team_hierarchy_recursive(isolated_db):
    """Create 3-member chain (A->B->C via delegation), verify depth."""
    team_id, member_ids = _create_team_with_members(
        isolated_db, ["agent-hier01", "agent-hier02", "agent-hier03"]
    )
    mA = member_ids["agent-hier01"]
    mB = member_ids["agent-hier02"]
    mC = member_ids["agent-hier03"]

    add_team_edge(team_id, mA, mB, edge_type="delegation")
    add_team_edge(team_id, mB, mC, edge_type="delegation")

    hierarchy = get_team_hierarchy(team_id, mA)
    assert len(hierarchy) == 2

    # B at depth 1
    b_entry = next(h for h in hierarchy if h["id"] == mB)
    assert b_entry["depth"] == 1

    # C at depth 2
    c_entry = next(h for h in hierarchy if h["id"] == mC)
    assert c_entry["depth"] == 2


# ---------------------------------------------------------------------------
# Test 9: Edge API endpoints
# ---------------------------------------------------------------------------


def test_edge_api_endpoints(client, isolated_db):
    """Using client: POST edge, GET edges, DELETE edge. Verify status codes."""
    _create_agent_in_db(isolated_db, "agent-api01", "API Agent 1")
    _create_agent_in_db(isolated_db, "agent-api02", "API Agent 2")

    # Create team
    resp = client.post("/admin/teams/", json={"name": "Edge API Team"})
    assert resp.status_code == 201
    team_id = resp.get_json()["team"]["id"]

    # Add members
    resp1 = client.post(
        f"/admin/teams/{team_id}/members",
        json={"agent_id": "agent-api01"},
    )
    assert resp1.status_code == 201
    m1_id = resp1.get_json()["member"]["id"]

    resp2 = client.post(
        f"/admin/teams/{team_id}/members",
        json={"agent_id": "agent-api02"},
    )
    assert resp2.status_code == 201
    m2_id = resp2.get_json()["member"]["id"]

    # POST edge
    resp = client.post(
        f"/admin/teams/{team_id}/edges",
        json={
            "source_member_id": m1_id,
            "target_member_id": m2_id,
            "edge_type": "delegation",
        },
    )
    assert resp.status_code == 201
    edge_data = resp.get_json()
    assert edge_data["message"] == "Edge created"
    edge_id = edge_data["edge"]["id"]

    # GET edges
    resp = client.get(f"/admin/teams/{team_id}/edges")
    assert resp.status_code == 200
    edges = resp.get_json()["edges"]
    assert len(edges) == 1
    assert edges[0]["source_member_id"] == m1_id

    # DELETE single edge
    resp = client.delete(f"/admin/teams/{team_id}/edges/{edge_id}")
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "Edge deleted"

    # Verify gone
    resp = client.get(f"/admin/teams/{team_id}/edges")
    assert len(resp.get_json()["edges"]) == 0


# ---------------------------------------------------------------------------
# Test 10: VALID_TOPOLOGIES extended
# ---------------------------------------------------------------------------


def test_valid_topologies_extended():
    """Verify VALID_TOPOLOGIES includes all 7 types."""
    expected = {
        "sequential",
        "parallel",
        "coordinator",
        "generator_critic",
        "hierarchical",
        "human_in_loop",
        "composite",
    }
    assert set(VALID_TOPOLOGIES) == expected


# ---------------------------------------------------------------------------
# Test 11: Mixed members in get_team_detail
# ---------------------------------------------------------------------------


def test_get_team_detail_mixed_members(isolated_db):
    """Create team with one agent and one super_agent member, verify both types."""
    _create_agent_in_db(isolated_db, "agent-mix01", "Agent Mix")
    _create_super_agent_in_db(isolated_db, "super-mix01", "SA Mix")

    team_id = add_team(name="Mixed Team")
    assert team_id is not None

    add_team_member(team_id=team_id, agent_id="agent-mix01")
    add_team_member(team_id=team_id, super_agent_id="super-mix01")

    detail = get_team_detail(team_id)
    assert detail is not None
    members = detail["members"]
    assert len(members) == 2

    agent_member = next(m for m in members if m["member_type"] == "agent")
    assert agent_member["agent_id"] == "agent-mix01"
    assert agent_member["agent_name"] == "Agent Mix"

    sa_member = next(m for m in members if m["member_type"] == "super_agent")
    assert sa_member["super_agent_id"] == "super-mix01"
    assert sa_member["super_agent_name"] == "SA Mix"


# ---------------------------------------------------------------------------
# Test 12: Topology endpoint accepts new types
# ---------------------------------------------------------------------------


def test_topology_endpoint_accepts_new_types(client, isolated_db):
    """PUT topology with 'hierarchical', verify 200 (not 400)."""
    resp = client.post("/admin/teams/", json={"name": "Hierarchical Team"})
    assert resp.status_code == 201
    team_id = resp.get_json()["team"]["id"]

    resp = client.put(
        f"/admin/teams/{team_id}/topology",
        json={"topology": "hierarchical"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["topology"] == "hierarchical"
