"""Tests for product owner features: migration, CRUD, meetings, dashboard."""

import json

from app.database import (
    get_product_detail,
)
from app.db import assign_team_to_project
from app.db.connection import get_connection
from app.db.projects import add_project
from app.db.teams import add_team, add_team_member

# =============================================================================
# Helpers
# =============================================================================


def _create_product(client, name="Test Product", **overrides):
    """Create a product via API."""
    data = {"name": name, "description": "Test product", **overrides}
    return client.post("/admin/products/", json=data)


def _create_super_agent(client, name="Owner Agent"):
    """Create a super_agent via API and return its ID."""
    resp = client.post(
        "/admin/super-agents/",
        json={"name": name, "description": "Test agent", "backend_type": "claude"},
    )
    return resp.get_json()["super_agent_id"]


# =============================================================================
# Migration v44 tests
# =============================================================================


class TestMigrationV44:
    def test_fresh_db_has_rationale_and_tags_json(self, isolated_db):
        """Fresh DB should have rationale and tags_json columns on product_decisions."""
        with get_connection() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(product_decisions)")}
        assert "rationale" in cols
        assert "tags_json" in cols

    def test_fresh_db_has_approved_status(self, isolated_db):
        """Fresh DB should use 'approved' (not 'accepted') in product_decisions CHECK."""
        with get_connection() as conn:
            sql_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='product_decisions'"
            ).fetchone()
        sql = sql_row[0]
        assert "'approved'" in sql
        assert "'accepted'" not in sql

    def test_fresh_db_has_milestone_columns(self, isolated_db):
        """Fresh DB should have sort_order, progress_pct, completed_date on product_milestones."""
        with get_connection() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(product_milestones)")}
        assert "sort_order" in cols
        assert "progress_pct" in cols
        assert "completed_date" in cols


# =============================================================================
# Decisions CRUD tests
# =============================================================================


class TestDecisionsCrud:
    def test_create_decision_with_rationale_and_tags(self, client):
        """POST creates a decision with rationale and tags fields."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        resp = client.post(
            f"/admin/products/{prod_id}/decisions",
            json={
                "title": "Use PostgreSQL",
                "description": "Switch to PG for production",
                "rationale": "Better concurrency support",
                "decision_type": "technical",
                "tags": ["database", "infrastructure"],
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["decision"]["title"] == "Use PostgreSQL"
        assert body["decision"]["rationale"] == "Better concurrency support"
        assert "database" in body["decision"]["tags_json"]

    def test_list_decisions(self, client):
        """GET returns all decisions for a product."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        client.post(f"/admin/products/{prod_id}/decisions", json={"title": "Decision A"})
        client.post(f"/admin/products/{prod_id}/decisions", json={"title": "Decision B"})

        resp = client.get(f"/admin/products/{prod_id}/decisions")
        assert resp.status_code == 200
        assert len(resp.get_json()["decisions"]) == 2

    def test_filter_decisions_by_status(self, client):
        """GET with ?status= filters decisions."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        # Create decision and update its status
        dec_resp = client.post(
            f"/admin/products/{prod_id}/decisions", json={"title": "Approved Decision"}
        )
        dec_id = dec_resp.get_json()["decision"]["id"]
        client.put(
            f"/admin/products/{prod_id}/decisions/{dec_id}",
            json={"status": "approved"},
        )

        client.post(f"/admin/products/{prod_id}/decisions", json={"title": "Proposed Decision"})

        resp = client.get(f"/admin/products/{prod_id}/decisions?status=approved")
        assert resp.status_code == 200
        decisions = resp.get_json()["decisions"]
        assert len(decisions) == 1
        assert decisions[0]["status"] == "approved"

    def test_filter_decisions_by_tag(self, client):
        """GET with ?tag= filters decisions by tag content."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        client.post(
            f"/admin/products/{prod_id}/decisions",
            json={"title": "DB Decision", "tags": ["database"]},
        )
        client.post(
            f"/admin/products/{prod_id}/decisions",
            json={"title": "UI Decision", "tags": ["frontend"]},
        )

        resp = client.get(f"/admin/products/{prod_id}/decisions?tag=database")
        assert resp.status_code == 200
        decisions = resp.get_json()["decisions"]
        assert len(decisions) == 1
        assert decisions[0]["title"] == "DB Decision"

    def test_update_decision(self, client):
        """PUT updates decision fields."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        dec_resp = client.post(f"/admin/products/{prod_id}/decisions", json={"title": "Initial"})
        dec_id = dec_resp.get_json()["decision"]["id"]

        resp = client.put(
            f"/admin/products/{prod_id}/decisions/{dec_id}",
            json={"title": "Updated", "rationale": "New rationale"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["decision"]["title"] == "Updated"
        assert resp.get_json()["decision"]["rationale"] == "New rationale"

    def test_delete_decision(self, client):
        """DELETE removes a decision."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        dec_resp = client.post(f"/admin/products/{prod_id}/decisions", json={"title": "To Delete"})
        dec_id = dec_resp.get_json()["decision"]["id"]

        resp = client.delete(f"/admin/products/{prod_id}/decisions/{dec_id}")
        assert resp.status_code == 200

        resp = client.get(f"/admin/products/{prod_id}/decisions/{dec_id}")
        assert resp.status_code == 404


# =============================================================================
# Milestones CRUD tests
# =============================================================================


class TestMilestonesCrud:
    def test_create_milestone_with_progress(self, client):
        """POST creates a milestone with sort_order and progress_pct."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        resp = client.post(
            f"/admin/products/{prod_id}/milestones",
            json={
                "version": "v1.0",
                "title": "First Release",
                "sort_order": 1,
                "progress_pct": 50,
                "target_date": "2026-03-01",
            },
        )
        assert resp.status_code == 201
        ms = resp.get_json()["milestone"]
        assert ms["sort_order"] == 1
        assert ms["progress_pct"] == 50

    def test_list_milestones_with_status_filter(self, client):
        """GET with ?status= filters milestones."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        ms_resp = client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v1.0", "title": "Active MS"},
        )
        ms_id = ms_resp.get_json()["milestone"]["id"]
        client.put(
            f"/admin/products/{prod_id}/milestones/{ms_id}",
            json={"status": "active"},
        )

        client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v2.0", "title": "Planning MS"},
        )

        resp = client.get(f"/admin/products/{prod_id}/milestones?status=active")
        assert resp.status_code == 200
        milestones = resp.get_json()["milestones"]
        assert len(milestones) == 1
        assert milestones[0]["title"] == "Active MS"

    def test_milestones_ordered_by_sort_order(self, client):
        """Milestones should be ordered by sort_order ASC."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v2.0", "title": "Second", "sort_order": 2},
        )
        client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v1.0", "title": "First", "sort_order": 1},
        )

        resp = client.get(f"/admin/products/{prod_id}/milestones")
        milestones = resp.get_json()["milestones"]
        assert milestones[0]["title"] == "First"
        assert milestones[1]["title"] == "Second"

    def test_update_milestone_with_completed_date(self, client):
        """PUT updates milestone with completed_date."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        ms_resp = client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v1.0", "title": "MS1"},
        )
        ms_id = ms_resp.get_json()["milestone"]["id"]

        resp = client.put(
            f"/admin/products/{prod_id}/milestones/{ms_id}",
            json={"progress_pct": 100, "completed_date": "2026-02-20", "status": "completed"},
        )
        assert resp.status_code == 200
        ms = resp.get_json()["milestone"]
        assert ms["progress_pct"] == 100
        assert ms["completed_date"] == "2026-02-20"

    def test_delete_milestone(self, client):
        """DELETE removes a milestone."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        ms_resp = client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v1.0", "title": "To Delete"},
        )
        ms_id = ms_resp.get_json()["milestone"]["id"]

        resp = client.delete(f"/admin/products/{prod_id}/milestones/{ms_id}")
        assert resp.status_code == 200

        resp = client.get(f"/admin/products/{prod_id}/milestones/{ms_id}")
        assert resp.status_code == 404


# =============================================================================
# Milestone-Project Junction tests
# =============================================================================


class TestMilestoneProjectJunction:
    def test_link_and_list_projects(self, client):
        """Link a project to a milestone and list it."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        proj_id = add_project(name="Test Proj", product_id=prod_id)

        ms_resp = client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v1.0", "title": "MS1"},
        )
        ms_id = ms_resp.get_json()["milestone"]["id"]

        link_resp = client.post(
            f"/admin/products/{prod_id}/milestones/{ms_id}/projects",
            json={"project_id": proj_id, "contribution": "Core feature"},
        )
        assert link_resp.status_code == 201

        list_resp = client.get(f"/admin/products/{prod_id}/milestones/{ms_id}/projects")
        assert list_resp.status_code == 200
        projects = list_resp.get_json()["projects"]
        assert len(projects) == 1
        assert projects[0]["project_id"] == proj_id

    def test_unlink_project(self, client):
        """Unlink a project from a milestone."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        proj_id = add_project(name="Test Proj", product_id=prod_id)

        ms_resp = client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v1.0", "title": "MS1"},
        )
        ms_id = ms_resp.get_json()["milestone"]["id"]

        client.post(
            f"/admin/products/{prod_id}/milestones/{ms_id}/projects",
            json={"project_id": proj_id},
        )

        resp = client.delete(f"/admin/products/{prod_id}/milestones/{ms_id}/projects/{proj_id}")
        assert resp.status_code == 200

        list_resp = client.get(f"/admin/products/{prod_id}/milestones/{ms_id}/projects")
        assert len(list_resp.get_json()["projects"]) == 0


# =============================================================================
# Owner Assignment tests
# =============================================================================


class TestOwnerAssignment:
    def test_assign_owner(self, client):
        """PUT /owner assigns a super_agent as product owner."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        sa_id = _create_super_agent(client, name="PO Agent")

        resp = client.put(
            f"/admin/products/{prod_id}/owner",
            json={"owner_agent_id": sa_id},
        )
        assert resp.status_code == 200
        assert resp.get_json()["product"]["owner_agent_id"] == sa_id

    def test_product_detail_includes_owner_agent_name(self, client):
        """GET product detail should include owner_agent_name from super_agents."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        sa_id = _create_super_agent(client, name="PO Agent")
        client.put(
            f"/admin/products/{prod_id}/owner",
            json={"owner_agent_id": sa_id},
        )

        detail = get_product_detail(prod_id)
        assert detail["owner_agent_id"] == sa_id
        assert detail["owner_agent_name"] == "PO Agent"


# =============================================================================
# Meeting Protocol tests
# =============================================================================


class TestMeetingProtocol:
    def test_trigger_standup_creates_messages(self, client):
        """POST /meetings/standup creates agent_messages with message_type=request, subject=standup."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        # Create owner super_agent
        owner_id = _create_super_agent(client, name="Owner Agent")
        client.put(f"/admin/products/{prod_id}/owner", json={"owner_agent_id": owner_id})

        # Create a project under this product
        proj_id = add_project(name="Test Proj", product_id=prod_id)

        # Create a leader super_agent and assign to project via team
        leader_id = _create_super_agent(client, name="Leader Agent")
        team_id = add_team(name="Test Team")
        add_team_member(team_id=team_id, name="Leader", super_agent_id=leader_id, tier="leader")
        assign_team_to_project(proj_id, team_id)

        resp = client.post(f"/admin/products/{prod_id}/meetings/standup")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["participants"] == 1
        assert len(body["message_ids"]) == 1

        # Verify the message in the DB
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM agent_messages WHERE id = ?", (body["message_ids"][0],)
            )
            msg = dict(cursor.fetchone())
        assert msg["from_agent_id"] == owner_id
        assert msg["to_agent_id"] == leader_id
        assert msg["message_type"] == "request"
        assert msg["subject"] == "standup"
        content = json.loads(msg["content"])
        assert content["type"] == "standup"

    def test_trigger_standup_no_owner_returns_400(self, client):
        """POST /meetings/standup on product without owner returns 400."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        resp = client.post(f"/admin/products/{prod_id}/meetings/standup")
        assert resp.status_code == 400
        assert "owner" in resp.get_json()["error"].lower()

    def test_trigger_standup_no_leaders_returns_zero_participants(self, client):
        """POST /meetings/standup with owner but no leaders returns participants=0."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        owner_id = _create_super_agent(client, name="Owner Agent")
        client.put(f"/admin/products/{prod_id}/owner", json={"owner_agent_id": owner_id})

        resp = client.post(f"/admin/products/{prod_id}/meetings/standup")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["participants"] == 0
        assert body["message_ids"] == []

    def test_meeting_history(self, client):
        """GET /meetings/history returns past standup messages."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        owner_id = _create_super_agent(client, name="Owner Agent")
        client.put(f"/admin/products/{prod_id}/owner", json={"owner_agent_id": owner_id})

        # Create a project with a leader to have actual messages
        proj_id = add_project(name="Test Proj", product_id=prod_id)
        leader_id = _create_super_agent(client, name="Leader Agent")
        team_id = add_team(name="Test Team")
        add_team_member(team_id=team_id, name="Leader", super_agent_id=leader_id, tier="leader")
        assign_team_to_project(proj_id, team_id)

        # Trigger a standup
        client.post(f"/admin/products/{prod_id}/meetings/standup")

        resp = client.get(f"/admin/products/{prod_id}/meetings/history")
        assert resp.status_code == 200
        meetings = resp.get_json()["meetings"]
        assert len(meetings) == 1
        assert meetings[0]["subject"] == "standup"


# =============================================================================
# Dashboard tests
# =============================================================================


class TestDashboard:
    def test_dashboard_returns_all_sections(self, client):
        """GET /dashboard returns product, decisions, milestones, health, activity, token_spend."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        # Add a decision
        client.post(
            f"/admin/products/{prod_id}/decisions",
            json={"title": "Test Decision"},
        )

        # Add a milestone
        client.post(
            f"/admin/products/{prod_id}/milestones",
            json={"version": "v1.0", "title": "MS1"},
        )

        # Add a project for health calculation
        add_project(name="Proj A", product_id=prod_id, status="active")

        resp = client.get(f"/admin/products/{prod_id}/dashboard")
        assert resp.status_code == 200
        body = resp.get_json()

        assert "product" in body
        assert "decisions" in body
        assert "milestones" in body
        assert "health" in body
        assert "activity" in body
        assert "token_spend" in body

        assert body["product"]["name"] == "Test Product"
        assert len(body["decisions"]) == 1
        assert len(body["milestones"]) == 1
        assert body["health"]["health"] == "green"

    def test_dashboard_health_yellow(self, client):
        """Dashboard health should be yellow when some projects are not active."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        add_project(name="Active Proj", product_id=prod_id, status="active")
        add_project(name="Active Proj 2", product_id=prod_id, status="active")
        add_project(name="Planning Proj", product_id=prod_id, status="planning")

        resp = client.get(f"/admin/products/{prod_id}/dashboard")
        body = resp.get_json()
        assert body["health"]["health"] == "yellow"

    def test_dashboard_health_red(self, client):
        """Dashboard health should be red when archived projects exist."""
        prod_resp = _create_product(client)
        prod_id = prod_resp.get_json()["product"]["id"]

        add_project(name="Active Proj", product_id=prod_id, status="active")
        add_project(name="Archived Proj", product_id=prod_id, status="archived")

        resp = client.get(f"/admin/products/{prod_id}/dashboard")
        body = resp.get_json()
        assert body["health"]["health"] == "red"

    def test_dashboard_not_found(self, client):
        """GET /dashboard for nonexistent product returns 404."""
        resp = client.get("/admin/products/prod-nonexist/dashboard")
        assert resp.status_code == 404
