"""Comprehensive scenario tests for advanced team-related route domains.

Covers: team_assignments, team_connections, team_edges, team_generation,
team_members, collaborative, product_owner, super_agents,
super_agent_documents, super_agent_exports.
"""

import tempfile
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_team(client, name="Alpha Team", description="Test team"):
    """Create a team and return its ID."""
    resp = client.post("/admin/teams/", json={"name": name, "description": description})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["team"]["id"]


def _create_product(client, name="Test Product", description="A product"):
    """Create a product and return its ID."""
    resp = client.post("/admin/products/", json={"name": name, "description": description})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["product"]["id"]


def _create_project(client, name="test-project", product_id=None):
    """Create a project and return its ID."""
    payload = {"name": name, "description": "A project"}
    if product_id:
        payload["product_id"] = product_id
    resp = client.post("/admin/projects/", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["project"]["id"]


def _create_super_agent(client, name="SA-Leader", **kwargs):
    """Create a super agent and return its ID."""
    payload = {"name": name, **kwargs}
    resp = client.post("/admin/super-agents/", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["super_agent_id"]


def _create_agent(client, name="Test Agent"):
    """Create an agent via API and return its ID."""
    resp = client.post("/admin/agents/", json={"name": name, "description": "test agent"})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["agent_id"]


def _add_team_member(client, team_id, name="Agent A", agent_id=None, **kwargs):
    """Add a member to a team and return the member ID."""
    payload = {"name": name, **kwargs}
    if agent_id:
        payload["agent_id"] = agent_id
    resp = client.post(f"/admin/teams/{team_id}/members", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["member"]["id"]


# ===========================================================================
# Team Members
# ===========================================================================


class TestTeamMembersScenario:
    """CRUD lifecycle for team members."""

    def test_add_list_update_delete_member(self, client):
        team_id = _create_team(client)

        # Add member
        resp = client.post(
            f"/admin/teams/{team_id}/members",
            json={"name": "Alice", "email": "alice@test.com", "role": "lead", "layer": "frontend"},
        )
        assert resp.status_code == 201
        member = resp.get_json()["member"]
        member_id = member["id"]
        assert member["name"] == "Alice"
        assert member["role"] == "lead"

        # List members
        resp = client.get(f"/admin/teams/{team_id}/members")
        assert resp.status_code == 200
        members = resp.get_json()["members"]
        assert any(m["id"] == member_id for m in members)

        # Update member
        resp = client.put(
            f"/admin/teams/{team_id}/members/{member_id}",
            json={"name": "Alice B.", "role": "member"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["member"]["name"] == "Alice B."

        # Delete member
        resp = client.delete(f"/admin/teams/{team_id}/members/{member_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = client.get(f"/admin/teams/{team_id}/members")
        assert all(m["id"] != member_id for m in resp.get_json()["members"])

    def test_add_member_missing_body(self, client):
        team_id = _create_team(client)
        resp = client.post(
            f"/admin/teams/{team_id}/members",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_add_member_no_identifier(self, client):
        team_id = _create_team(client)
        resp = client.post(f"/admin/teams/{team_id}/members", json={"email": "x@y.com"})
        assert resp.status_code in (400, 415)

    def test_update_nonexistent_member(self, client):
        team_id = _create_team(client)
        resp = client.put(f"/admin/teams/{team_id}/members/99999", json={"name": "Ghost"})
        assert resp.status_code == 404

    def test_delete_nonexistent_member(self, client):
        team_id = _create_team(client)
        resp = client.delete(f"/admin/teams/{team_id}/members/99999")
        assert resp.status_code == 404

    def test_add_member_with_super_agent_id(self, client):
        team_id = _create_team(client)
        sa_id = _create_super_agent(client, name="SA-Member")
        resp = client.post(
            f"/admin/teams/{team_id}/members",
            json={"super_agent_id": sa_id, "role": "executor"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["member"]["super_agent_id"] == sa_id


# ===========================================================================
# Team Edges
# ===========================================================================


class TestTeamEdgesScenario:
    """Directed graph edges between team members."""

    def test_create_list_delete_edge(self, client):
        team_id = _create_team(client)
        m1 = _add_team_member(client, team_id, name="Node-A")
        m2 = _add_team_member(client, team_id, name="Node-B")

        # Create edge
        resp = client.post(
            f"/admin/teams/{team_id}/edges",
            json={
                "source_member_id": m1,
                "target_member_id": m2,
                "edge_type": "delegation",
                "label": "delegates to",
                "weight": 2,
            },
        )
        assert resp.status_code == 201
        edge = resp.get_json()["edge"]
        edge_id = edge["id"]
        assert edge["edge_type"] == "delegation"

        # List edges
        resp = client.get(f"/admin/teams/{team_id}/edges")
        assert resp.status_code == 200
        assert any(e["id"] == edge_id for e in resp.get_json()["edges"])

        # Delete edge
        resp = client.delete(f"/admin/teams/{team_id}/edges/{edge_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = client.get(f"/admin/teams/{team_id}/edges")
        assert all(e["id"] != edge_id for e in resp.get_json()["edges"])

    def test_create_edge_invalid_type(self, client):
        team_id = _create_team(client)
        m1 = _add_team_member(client, team_id, name="X")
        m2 = _add_team_member(client, team_id, name="Y")
        resp = client.post(
            f"/admin/teams/{team_id}/edges",
            json={"source_member_id": m1, "target_member_id": m2, "edge_type": "invalid_type"},
        )
        assert resp.status_code in (400, 415)

    def test_create_edge_missing_fields(self, client):
        team_id = _create_team(client)
        resp = client.post(f"/admin/teams/{team_id}/edges", json={"source_member_id": 1})
        assert resp.status_code in (400, 415)

    def test_create_edge_no_body(self, client):
        team_id = _create_team(client)
        resp = client.post(
            f"/admin/teams/{team_id}/edges",
            data="bad",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_self_loop_rejected(self, client):
        team_id = _create_team(client)
        m1 = _add_team_member(client, team_id, name="Self")
        resp = client.post(
            f"/admin/teams/{team_id}/edges",
            json={"source_member_id": m1, "target_member_id": m1, "edge_type": "delegation"},
        )
        assert resp.status_code in (400, 415)

    def test_bulk_delete_edges(self, client):
        team_id = _create_team(client)
        m1 = _add_team_member(client, team_id, name="A")
        m2 = _add_team_member(client, team_id, name="B")
        m3 = _add_team_member(client, team_id, name="C")

        client.post(
            f"/admin/teams/{team_id}/edges",
            json={"source_member_id": m1, "target_member_id": m2, "edge_type": "delegation"},
        )
        client.post(
            f"/admin/teams/{team_id}/edges",
            json={"source_member_id": m2, "target_member_id": m3, "edge_type": "reporting"},
        )

        resp = client.delete(f"/admin/teams/{team_id}/edges")
        assert resp.status_code == 200
        assert resp.get_json()["deleted_count"] == 2

    def test_delete_nonexistent_edge(self, client):
        team_id = _create_team(client)
        resp = client.delete(f"/admin/teams/{team_id}/edges/99999")
        assert resp.status_code == 404

    def test_all_valid_edge_types(self, client):
        """All four valid edge types can be created."""
        team_id = _create_team(client)
        members = []
        for i in range(5):
            members.append(_add_team_member(client, team_id, name=f"M{i}"))

        for i, etype in enumerate(["delegation", "reporting", "messaging", "approval_gate"]):
            resp = client.post(
                f"/admin/teams/{team_id}/edges",
                json={
                    "source_member_id": members[i],
                    "target_member_id": members[i + 1],
                    "edge_type": etype,
                },
            )
            assert resp.status_code == 201, f"Failed for edge_type={etype}"


# ===========================================================================
# Team Connections
# ===========================================================================


class TestTeamConnectionsScenario:
    """Inter-team connection management."""

    def test_create_list_delete_connection(self, client):
        team_a = _create_team(client, name="Team A")
        team_b = _create_team(client, name="Team B")

        # Create connection
        resp = client.post(
            f"/admin/teams/{team_a}/connections",
            json={
                "target_team_id": team_b,
                "connection_type": "dependency",
                "description": "A depends on B",
            },
        )
        assert resp.status_code == 201
        conn_id = resp.get_json()["id"]

        # List connections
        resp = client.get(f"/admin/teams/{team_a}/connections")
        assert resp.status_code == 200
        conns = resp.get_json()["connections"]
        assert any(c["id"] == conn_id for c in conns)

        # Delete connection
        resp = client.delete(f"/admin/teams/{team_a}/connections/{conn_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = client.get(f"/admin/teams/{team_a}/connections")
        assert all(c["id"] != conn_id for c in resp.get_json()["connections"])

    def test_delete_nonexistent_connection(self, client):
        team_id = _create_team(client)
        resp = client.delete(f"/admin/teams/{team_id}/connections/99999")
        assert resp.status_code == 404

    def test_connection_visible_from_target(self, client):
        """Connection is visible from the target team too."""
        team_a = _create_team(client, name="Source")
        team_b = _create_team(client, name="Target")
        resp = client.post(
            f"/admin/teams/{team_a}/connections",
            json={"target_team_id": team_b, "connection_type": "dependency"},
        )
        assert resp.status_code == 201

        resp = client.get(f"/admin/teams/{team_b}/connections")
        assert resp.status_code == 200
        assert len(resp.get_json()["connections"]) >= 1


# ===========================================================================
# Team Assignments
# ===========================================================================


class TestTeamAssignmentsScenario:
    """Agent assignment (skill/command/hook/rule) management within teams."""

    def _setup_team_with_agent_member(self, client):
        """Create team, add a member with a real agent_id, return (team_id, agent_id)."""
        team_id = _create_team(client)
        agent_id = _create_agent(client, name="AssignmentAgent")
        _add_team_member(client, team_id, name="AssignmentAgent", agent_id=agent_id)
        return team_id, agent_id

    def test_add_and_list_assignment(self, client):
        team_id, agent_id = self._setup_team_with_agent_member(client)

        resp = client.post(
            f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
            json={"entity_type": "skill", "entity_id": "skill-abc", "entity_name": "Deploy Skill"},
        )
        assert resp.status_code == 201
        assignment = resp.get_json()["assignment"]
        assert assignment["entity_type"] == "skill"

        # List for agent
        resp = client.get(f"/admin/teams/{team_id}/agents/{agent_id}/assignments")
        assert resp.status_code == 200
        assert len(resp.get_json()["assignments"]) == 1

        # List for whole team
        resp = client.get(f"/admin/teams/{team_id}/assignments")
        assert resp.status_code == 200
        assert len(resp.get_json()["assignments"]) == 1

    def test_delete_single_assignment(self, client):
        team_id, agent_id = self._setup_team_with_agent_member(client)

        resp = client.post(
            f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
            json={"entity_type": "command", "entity_id": "cmd-1"},
        )
        assignment_id = resp.get_json()["assignment"]["id"]

        resp = client.delete(f"/admin/teams/{team_id}/assignments/{assignment_id}")
        assert resp.status_code == 200

        resp = client.get(f"/admin/teams/{team_id}/agents/{agent_id}/assignments")
        assert len(resp.get_json()["assignments"]) == 0

    def test_bulk_delete_assignments(self, client):
        team_id, agent_id = self._setup_team_with_agent_member(client)

        for etype in ("skill", "hook"):
            client.post(
                f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
                json={"entity_type": etype, "entity_id": f"{etype}-1"},
            )

        resp = client.delete(f"/admin/teams/{team_id}/agents/{agent_id}/assignments")
        assert resp.status_code == 200
        assert resp.get_json()["deleted_count"] == 2

    def test_bulk_delete_by_entity_type(self, client):
        team_id, agent_id = self._setup_team_with_agent_member(client)

        for i, etype in enumerate(("skill", "hook", "skill")):
            client.post(
                f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
                json={"entity_type": etype, "entity_id": f"{etype}-{i}"},
            )

        resp = client.delete(
            f"/admin/teams/{team_id}/agents/{agent_id}/assignments?entity_type=skill"
        )
        assert resp.status_code == 200
        assert resp.get_json()["deleted_count"] == 2

    def test_assignment_invalid_entity_type(self, client):
        team_id, agent_id = self._setup_team_with_agent_member(client)
        resp = client.post(
            f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
            json={"entity_type": "bad_type", "entity_id": "x"},
        )
        assert resp.status_code in (400, 415)

    def test_assignment_missing_fields(self, client):
        team_id, agent_id = self._setup_team_with_agent_member(client)
        resp = client.post(
            f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
            json={"entity_type": "skill"},
        )
        assert resp.status_code in (400, 415)

    def test_assignment_no_body(self, client):
        team_id, agent_id = self._setup_team_with_agent_member(client)
        resp = client.post(
            f"/admin/teams/{team_id}/agents/{agent_id}/assignments",
            data="nope",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_assignment_nonexistent_team(self, client):
        resp = client.post(
            "/admin/teams/team-nonexist/agents/agent-xxx/assignments",
            json={"entity_type": "skill", "entity_id": "s1"},
        )
        assert resp.status_code == 404

    def test_assignment_agent_not_member(self, client):
        team_id = _create_team(client)
        resp = client.post(
            f"/admin/teams/{team_id}/agents/agent-notin/assignments",
            json={"entity_type": "skill", "entity_id": "s1"},
        )
        assert resp.status_code in (400, 415)

    def test_delete_nonexistent_assignment(self, client):
        team_id = _create_team(client)
        resp = client.delete(f"/admin/teams/{team_id}/assignments/99999")
        assert resp.status_code == 404


# ===========================================================================
# Team Generation
# ===========================================================================


class TestTeamGenerationScenario:
    """AI-powered team generation (async job pattern)."""

    def test_generate_returns_job_id(self, client):
        resp = client.post(
            "/admin/teams/generate",
            json={"description": "A backend team for microservices development"},
        )
        assert resp.status_code == 202
        body = resp.get_json()
        assert "job_id" in body
        assert body["job_id"].startswith("gen-")

    def test_generate_short_description_rejected(self, client):
        resp = client.post("/admin/teams/generate", json={"description": "short"})
        assert resp.status_code in (400, 415)

    def test_generate_no_body(self, client):
        resp = client.post(
            "/admin/teams/generate", data="bad", content_type="text/plain"
        )
        assert resp.status_code in (400, 415)

    def test_poll_nonexistent_job(self, client):
        resp = client.get("/admin/teams/generate/gen-doesnotexist")
        assert resp.status_code == 404

    def test_poll_pending_job(self, client):
        """After creating a job, polling immediately returns pending status."""
        # Patch the service so the thread doesn't actually run
        with patch(
            "app.routes.team_generation.TeamGenerationService.generate",
            side_effect=lambda d: (_ for _ in ()).throw(RuntimeError("test")),
        ):
            resp = client.post(
                "/admin/teams/generate",
                json={"description": "A team for frontend development with React expertise"},
            )
            job_id = resp.get_json()["job_id"]

        # The job should exist (pending or error, depending on thread timing)
        resp = client.get(f"/admin/teams/generate/{job_id}")
        assert resp.status_code in (200, 500)

    def test_stream_short_description_rejected(self, client):
        resp = client.post("/admin/teams/generate/stream", json={"description": "too short"})
        assert resp.status_code in (400, 415)

    def test_stream_no_body(self, client):
        resp = client.post(
            "/admin/teams/generate/stream", data="nope", content_type="text/plain"
        )
        assert resp.status_code in (400, 415)


# ===========================================================================
# Collaborative Viewer
# ===========================================================================


class TestCollaborativeViewerScenario:
    """Live collaborative execution viewing with presence and comments."""

    def test_join_leave_viewers(self, client):
        exec_id = "exec-test-001"

        # Join
        resp = client.post(
            f"/admin/executions/{exec_id}/viewers/join",
            json={"viewer_id": "v1", "name": "Alice"},
        )
        assert resp.status_code == 200
        viewers = resp.get_json()["viewers"]
        assert any(v["viewer_id"] == "v1" for v in viewers)

        # Second viewer joins
        resp = client.post(
            f"/admin/executions/{exec_id}/viewers/join",
            json={"viewer_id": "v2", "name": "Bob"},
        )
        assert resp.status_code == 200
        assert len(resp.get_json()["viewers"]) == 2

        # List viewers
        resp = client.get(f"/admin/executions/{exec_id}/viewers")
        assert resp.status_code == 200
        assert len(resp.get_json()["viewers"]) == 2

        # Leave
        resp = client.post(
            f"/admin/executions/{exec_id}/viewers/leave",
            json={"viewer_id": "v1"},
        )
        assert resp.status_code == 200

        # Verify v1 gone
        resp = client.get(f"/admin/executions/{exec_id}/viewers")
        viewers = resp.get_json()["viewers"]
        assert not any(v["viewer_id"] == "v1" for v in viewers)

    def test_heartbeat(self, client):
        exec_id = "exec-test-hb"
        client.post(
            f"/admin/executions/{exec_id}/viewers/join",
            json={"viewer_id": "v1", "name": "Hb-User"},
        )
        resp = client.post(
            f"/admin/executions/{exec_id}/viewers/heartbeat",
            json={"viewer_id": "v1"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_join_missing_fields(self, client):
        resp = client.post(
            "/admin/executions/exec-x/viewers/join",
            json={"viewer_id": "v1"},
        )
        assert resp.status_code in (400, 415)

    def test_leave_missing_viewer_id(self, client):
        resp = client.post("/admin/executions/exec-x/viewers/leave", json={})
        assert resp.status_code in (400, 415)

    def test_heartbeat_missing_viewer_id(self, client):
        resp = client.post("/admin/executions/exec-x/viewers/heartbeat", json={})
        assert resp.status_code in (400, 415)

    def test_post_and_list_and_delete_comment(self, client):
        exec_id = "exec-test-comments"

        # Create an execution_log row so the FK constraint is satisfied
        from app.database import get_connection

        with get_connection() as conn:
            conn.execute(
                """INSERT INTO execution_logs
                   (execution_id, trigger_id, trigger_type, started_at, backend_type, status)
                   VALUES (?, 'bot-security', 'manual', datetime('now'), 'claude', 'running')""",
                (exec_id,),
            )
            conn.commit()

        # Post comment
        resp = client.post(
            f"/admin/executions/{exec_id}/comments",
            json={
                "viewer_id": "v1",
                "viewer_name": "Alice",
                "line_number": 5,
                "content": "This line looks suspicious",
            },
        )
        assert resp.status_code == 201
        comment = resp.get_json()
        comment_id = comment["id"]

        # List comments
        resp = client.get(f"/admin/executions/{exec_id}/comments")
        assert resp.status_code == 200
        comments = resp.get_json()["comments"]
        assert any(c["id"] == comment_id for c in comments)

        # Delete comment
        resp = client.delete(f"/admin/comments/{comment_id}")
        assert resp.status_code == 200

        # Verify deleted
        resp = client.get(f"/admin/executions/{exec_id}/comments")
        assert all(c["id"] != comment_id for c in resp.get_json()["comments"])

    def test_post_comment_missing_fields(self, client):
        resp = client.post(
            "/admin/executions/exec-x/comments",
            json={"viewer_id": "v1", "viewer_name": "Bob"},
        )
        assert resp.status_code in (400, 415)

    def test_delete_nonexistent_comment(self, client):
        resp = client.delete("/admin/comments/comment-nonexist")
        assert resp.status_code == 404


# ===========================================================================
# Product Owner
# ===========================================================================


class TestProductOwnerScenario:
    """Product owner decisions, milestones, meetings, and dashboard."""

    # -- Decisions --

    def test_decision_crud(self, client):
        product_id = _create_product(client)

        # Create
        resp = client.post(
            f"/admin/products/{product_id}/decisions",
            json={
                "title": "Use PostgreSQL",
                "description": "Switch from SQLite to PostgreSQL",
                "rationale": "Better concurrency",
                "decision_type": "technical",
                "tags": ["database", "infra"],
            },
        )
        assert resp.status_code == 201
        decision = resp.get_json()["decision"]
        decision_id = decision["id"]

        # Read
        resp = client.get(f"/admin/products/{product_id}/decisions/{decision_id}")
        assert resp.status_code == 200
        assert resp.get_json()["decision"]["title"] == "Use PostgreSQL"

        # Update
        resp = client.put(
            f"/admin/products/{product_id}/decisions/{decision_id}",
            json={"status": "approved", "decided_by": "CTO"},
        )
        assert resp.status_code == 200

        # List
        resp = client.get(f"/admin/products/{product_id}/decisions")
        assert resp.status_code == 200
        assert resp.get_json()["total_count"] >= 1

        # Delete
        resp = client.delete(f"/admin/products/{product_id}/decisions/{decision_id}")
        assert resp.status_code == 200

    def test_decision_missing_title(self, client):
        product_id = _create_product(client)
        resp = client.post(
            f"/admin/products/{product_id}/decisions",
            json={"description": "no title"},
        )
        assert resp.status_code in (400, 415)

    def test_decision_nonexistent_product(self, client):
        resp = client.get("/admin/products/prod-nope/decisions")
        assert resp.status_code == 404

    def test_get_nonexistent_decision(self, client):
        product_id = _create_product(client)
        resp = client.get(f"/admin/products/{product_id}/decisions/dec-nope")
        assert resp.status_code == 404

    def test_delete_nonexistent_decision(self, client):
        product_id = _create_product(client)
        resp = client.delete(f"/admin/products/{product_id}/decisions/dec-nope")
        assert resp.status_code == 404

    # -- Milestones --

    def test_milestone_crud(self, client):
        product_id = _create_product(client)

        # Create
        resp = client.post(
            f"/admin/products/{product_id}/milestones",
            json={
                "version": "v1.0",
                "title": "Initial Release",
                "description": "First public release",
                "target_date": "2026-06-01",
            },
        )
        assert resp.status_code == 201
        milestone = resp.get_json()["milestone"]
        milestone_id = milestone["id"]

        # Read
        resp = client.get(f"/admin/products/{product_id}/milestones/{milestone_id}")
        assert resp.status_code == 200
        assert resp.get_json()["milestone"]["version"] == "v1.0"

        # Update
        resp = client.put(
            f"/admin/products/{product_id}/milestones/{milestone_id}",
            json={"progress_pct": 50, "status": "in_progress"},
        )
        assert resp.status_code == 200

        # List
        resp = client.get(f"/admin/products/{product_id}/milestones")
        assert resp.status_code == 200
        assert resp.get_json()["total_count"] >= 1

        # Delete
        resp = client.delete(f"/admin/products/{product_id}/milestones/{milestone_id}")
        assert resp.status_code == 200

    def test_milestone_missing_fields(self, client):
        product_id = _create_product(client)
        resp = client.post(
            f"/admin/products/{product_id}/milestones",
            json={"version": "v1.0"},
        )
        assert resp.status_code in (400, 415)

    def test_get_nonexistent_milestone(self, client):
        product_id = _create_product(client)
        resp = client.get(f"/admin/products/{product_id}/milestones/ms-nope")
        assert resp.status_code == 404

    def test_delete_nonexistent_milestone(self, client):
        product_id = _create_product(client)
        resp = client.delete(f"/admin/products/{product_id}/milestones/ms-nope")
        assert resp.status_code == 404

    # -- Milestone-Project Junction --

    def test_link_and_unlink_project_to_milestone(self, client):
        product_id = _create_product(client)
        project_id = _create_project(client, name="linked-proj", product_id=product_id)

        resp = client.post(
            f"/admin/products/{product_id}/milestones",
            json={"version": "v2.0", "title": "Second Release"},
        )
        milestone_id = resp.get_json()["milestone"]["id"]

        # Link
        resp = client.post(
            f"/admin/products/{product_id}/milestones/{milestone_id}/projects",
            json={"project_id": project_id, "contribution": "Core API"},
        )
        assert resp.status_code == 201

        # List
        resp = client.get(
            f"/admin/products/{product_id}/milestones/{milestone_id}/projects"
        )
        assert resp.status_code == 200
        assert resp.get_json()["total_count"] >= 1

        # Unlink
        resp = client.delete(
            f"/admin/products/{product_id}/milestones/{milestone_id}/projects/{project_id}"
        )
        assert resp.status_code == 200

    def test_link_project_missing_id(self, client):
        product_id = _create_product(client)
        resp = client.post(
            f"/admin/products/{product_id}/milestones",
            json={"version": "v3.0", "title": "Third"},
        )
        milestone_id = resp.get_json()["milestone"]["id"]

        resp = client.post(
            f"/admin/products/{product_id}/milestones/{milestone_id}/projects",
            json={},
        )
        assert resp.status_code in (400, 415)

    def test_unlink_nonexistent(self, client):
        product_id = _create_product(client)
        resp = client.post(
            f"/admin/products/{product_id}/milestones",
            json={"version": "v4.0", "title": "Fourth"},
        )
        milestone_id = resp.get_json()["milestone"]["id"]

        resp = client.delete(
            f"/admin/products/{product_id}/milestones/{milestone_id}/projects/proj-nope"
        )
        assert resp.status_code == 404

    # -- Owner Assignment --

    def test_assign_owner(self, client):
        product_id = _create_product(client)
        sa_id = _create_super_agent(client, name="Owner-Agent")

        resp = client.put(
            f"/admin/products/{product_id}/owner",
            json={"owner_agent_id": sa_id},
        )
        assert resp.status_code == 200
        assert resp.get_json()["product"]["owner_agent_id"] == sa_id

    def test_assign_owner_missing_field(self, client):
        product_id = _create_product(client)
        resp = client.put(f"/admin/products/{product_id}/owner", json={})
        assert resp.status_code in (400, 415)

    def test_assign_owner_nonexistent_product(self, client):
        resp = client.put(
            "/admin/products/prod-nope/owner", json={"owner_agent_id": "sa-1"}
        )
        assert resp.status_code == 404

    # -- Meetings --

    def test_standup_no_owner(self, client):
        product_id = _create_product(client)
        resp = client.post(f"/admin/products/{product_id}/meetings/standup")
        assert resp.status_code in (400, 415)

    def test_meeting_history_empty(self, client):
        product_id = _create_product(client)
        resp = client.get(f"/admin/products/{product_id}/meetings/history")
        assert resp.status_code == 200
        assert resp.get_json()["meetings"] == []

    def test_meeting_history_nonexistent_product(self, client):
        resp = client.get("/admin/products/prod-nope/meetings/history")
        assert resp.status_code == 404

    # -- Dashboard --

    def test_dashboard(self, client):
        product_id = _create_product(client)
        resp = client.get(f"/admin/products/{product_id}/dashboard")
        assert resp.status_code == 200

    def test_dashboard_nonexistent_product(self, client):
        resp = client.get("/admin/products/prod-nope/dashboard")
        assert resp.status_code == 404


# ===========================================================================
# Super Agents
# ===========================================================================


class TestSuperAgentsScenario:
    """SuperAgent CRUD lifecycle."""

    def test_create_list_get_update_delete(self, client):
        # Create
        resp = client.post(
            "/admin/super-agents/",
            json={
                "name": "Orchestrator",
                "description": "Top-level orchestrator",
                "backend_type": "claude",
                "preferred_model": "opus",
                "max_concurrent_sessions": 5,
            },
        )
        assert resp.status_code == 201
        sa_id = resp.get_json()["super_agent_id"]

        # List
        resp = client.get("/admin/super-agents/")
        assert resp.status_code == 200
        assert resp.get_json()["total_count"] >= 1

        # Get
        resp = client.get(f"/admin/super-agents/{sa_id}")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Orchestrator"

        # Update
        resp = client.put(
            f"/admin/super-agents/{sa_id}",
            json={"description": "Updated desc", "enabled": True},
        )
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/admin/super-agents/{sa_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = client.get(f"/admin/super-agents/{sa_id}")
        assert resp.status_code == 404

    def test_create_missing_name(self, client):
        resp = client.post("/admin/super-agents/", json={"description": "No name"})
        assert resp.status_code in (400, 415)

    def test_create_no_body(self, client):
        resp = client.post(
            "/admin/super-agents/", data="bad", content_type="text/plain"
        )
        assert resp.status_code in (400, 415)

    def test_update_nonexistent(self, client):
        resp = client.put(
            "/admin/super-agents/sa-nope", json={"description": "ghost"}
        )
        assert resp.status_code == 404

    def test_update_no_body(self, client):
        sa_id = _create_super_agent(client, name="NoBody-SA")
        resp = client.put(
            f"/admin/super-agents/{sa_id}",
            data="bad",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_delete_nonexistent(self, client):
        resp = client.delete("/admin/super-agents/sa-nope")
        assert resp.status_code == 404

    def test_create_with_parent_hierarchy(self, client):
        parent_id = _create_super_agent(client, name="Parent-SA")
        resp = client.post(
            "/admin/super-agents/",
            json={"name": "Child-SA", "parent_super_agent_id": parent_id},
        )
        assert resp.status_code == 201


# ===========================================================================
# Super Agent Documents
# ===========================================================================


class TestSuperAgentDocumentsScenario:
    """Document management for super agents."""

    def test_create_list_get_update_delete_document(self, client):
        sa_id = _create_super_agent(client, name="Doc-SA")

        # Create
        resp = client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={
                "doc_type": "SOUL",
                "title": "Core Identity",
                "content": "You are a careful orchestrator.",
            },
        )
        assert resp.status_code == 201
        doc_id = resp.get_json()["document_id"]

        # List
        resp = client.get(f"/admin/super-agents/{sa_id}/documents")
        assert resp.status_code == 200
        assert len(resp.get_json()["documents"]) >= 1

        # Get
        resp = client.get(f"/admin/super-agents/{sa_id}/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "Core Identity"

        # Update
        resp = client.put(
            f"/admin/super-agents/{sa_id}/documents/{doc_id}",
            json={"title": "Updated Identity", "content": "Updated content."},
        )
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/admin/super-agents/{sa_id}/documents/{doc_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = client.get(f"/admin/super-agents/{sa_id}/documents/{doc_id}")
        assert resp.status_code == 404

    def test_create_document_missing_doc_type(self, client):
        sa_id = _create_super_agent(client, name="DocMissing-SA")
        resp = client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"title": "No Type"},
        )
        assert resp.status_code in (400, 415)

    def test_create_document_missing_title(self, client):
        sa_id = _create_super_agent(client, name="DocNoTitle-SA")
        resp = client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"doc_type": "SOUL"},
        )
        assert resp.status_code in (400, 415)

    def test_create_document_invalid_type(self, client):
        sa_id = _create_super_agent(client, name="DocBadType-SA")
        resp = client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"doc_type": "INVALID", "title": "Bad"},
        )
        assert resp.status_code in (400, 415)

    def test_create_document_no_body(self, client):
        sa_id = _create_super_agent(client, name="DocNoBody-SA")
        resp = client.post(
            f"/admin/super-agents/{sa_id}/documents",
            data="bad",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_update_nonexistent_document(self, client):
        sa_id = _create_super_agent(client, name="DocUpdate-SA")
        resp = client.put(
            f"/admin/super-agents/{sa_id}/documents/99999",
            json={"title": "Ghost"},
        )
        assert resp.status_code == 404

    def test_update_document_no_body(self, client):
        sa_id = _create_super_agent(client, name="DocUpdateNB-SA")
        resp = client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"doc_type": "IDENTITY", "title": "ID Doc", "content": "test"},
        )
        doc_id = resp.get_json()["document_id"]
        resp = client.put(
            f"/admin/super-agents/{sa_id}/documents/{doc_id}",
            data="bad",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_delete_nonexistent_document(self, client):
        sa_id = _create_super_agent(client, name="DocDel-SA")
        resp = client.delete(f"/admin/super-agents/{sa_id}/documents/99999")
        assert resp.status_code == 404

    def test_all_valid_doc_types(self, client):
        """All four valid document types can be created."""
        sa_id = _create_super_agent(client, name="AllDocs-SA")
        for dtype in ("SOUL", "IDENTITY", "MEMORY", "ROLE"):
            resp = client.post(
                f"/admin/super-agents/{sa_id}/documents",
                json={"doc_type": dtype, "title": f"{dtype} Doc", "content": f"{dtype} content"},
            )
            assert resp.status_code == 201, f"Failed for doc_type={dtype}"


# ===========================================================================
# Super Agent Exports
# ===========================================================================


class TestSuperAgentExportsScenario:
    """Export/import/validate super agent packages."""

    def test_export_directory_format(self, client):
        sa_id = _create_super_agent(client, name="Export-SA")
        # Add a document so export has content
        client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"doc_type": "SOUL", "title": "Soul", "content": "You are an exporter."},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sa_id,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["format"] == "directory"
            assert "export_path" in body

    def test_export_zip_format(self, client):
        sa_id = _create_super_agent(client, name="ZipExport-SA")
        client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"doc_type": "IDENTITY", "title": "ID", "content": "identity"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sa_id,
                    "export_format": "zip",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["format"] == "zip"

    def test_export_missing_super_agent_id(self, client):
        resp = client.post(
            "/admin/super-agent-exports/export",
            json={"export_format": "zip"},
        )
        assert resp.status_code in (400, 415)

    def test_export_invalid_format(self, client):
        sa_id = _create_super_agent(client, name="BadFormat-SA")
        resp = client.post(
            "/admin/super-agent-exports/export",
            json={"super_agent_id": sa_id, "export_format": "tar"},
        )
        assert resp.status_code in (400, 415)

    def test_export_nonexistent_super_agent(self, client):
        resp = client.post(
            "/admin/super-agent-exports/export",
            json={"super_agent_id": "sa-nope", "export_format": "zip"},
        )
        assert resp.status_code == 404

    def test_export_no_body(self, client):
        resp = client.post(
            "/admin/super-agent-exports/export",
            data="bad",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_import_and_roundtrip(self, client):
        """Export then import should create a new super agent."""
        sa_id = _create_super_agent(client, name="Roundtrip-SA")
        client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"doc_type": "SOUL", "title": "Soul", "content": "soul content"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Export
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sa_id,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            export_path = resp.get_json()["export_path"]

            # Import
            resp = client.post(
                "/admin/super-agent-exports/import",
                json={"source_path": export_path},
            )
            assert resp.status_code == 201
            body = resp.get_json()
            assert "super_agent_id" in body

    def test_import_missing_source_path(self, client):
        resp = client.post("/admin/super-agent-exports/import", json={})
        assert resp.status_code in (400, 415)

    def test_import_no_body(self, client):
        resp = client.post(
            "/admin/super-agent-exports/import",
            data="bad",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_validate_missing_source_path(self, client):
        resp = client.post("/admin/super-agent-exports/validate", json={})
        assert resp.status_code in (400, 415)

    def test_validate_no_body(self, client):
        resp = client.post(
            "/admin/super-agent-exports/validate",
            data="bad",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    def test_validate_missing_manifest(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/validate",
                json={"source_path": tmpdir},
            )
            assert resp.status_code == 404

    def test_validate_valid_manifest(self, client):
        """Export a super agent, then validate the exported package."""
        sa_id = _create_super_agent(client, name="Validate-SA")
        client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"doc_type": "SOUL", "title": "Soul", "content": "soul"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sa_id,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            export_path = resp.get_json()["export_path"]

            resp = client.post(
                "/admin/super-agent-exports/validate",
                json={"source_path": export_path},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert "valid" in body

    def test_zip_roundtrip(self, client):
        """Export as zip, then import from zip."""
        sa_id = _create_super_agent(client, name="ZipRoundtrip-SA")
        client.post(
            f"/admin/super-agents/{sa_id}/documents",
            json={"doc_type": "ROLE", "title": "Role", "content": "role content"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Export as zip
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sa_id,
                    "export_format": "zip",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            zip_path = resp.get_json()["export_path"]

            # Import from zip
            resp = client.post(
                "/admin/super-agent-exports/import",
                json={"source_path": zip_path},
            )
            assert resp.status_code == 201
            assert "super_agent_id" in resp.get_json()
