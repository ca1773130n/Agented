"""Tests for /admin/projects/<project_id>/instances API routes."""

from unittest.mock import patch

from app.db.project_sa_instances import create_project_sa_instance, get_project_sa_instance
from app.db.projects import create_project
from app.db.super_agents import create_super_agent
from app.db.teams import create_team


def _setup_project_and_sa(isolated_db):
    """Helper: create a project and super agent, return (project_id, sa_id)."""
    proj_id = create_project(name="Test Project")
    sa_id = create_super_agent(name="Test SA", backend_type="claude")
    return proj_id, sa_id


# =============================================================================
# POST /<project_id>/instances — Create instances
# =============================================================================


class TestCreateInstance:
    @patch("app.services.instance_service.InstanceService._create_worktree_for_instance")
    @patch("app.services.instance_service.InstanceService._create_initial_session")
    def test_create_sa_instance(self, mock_session, mock_worktree, client, isolated_db):
        """POST with super_agent_id creates an SA instance and returns 201."""
        mock_worktree.return_value = None
        mock_session.return_value = None

        proj_id, sa_id = _setup_project_and_sa(isolated_db)
        resp = client.post(
            f"/admin/projects/{proj_id}/instances",
            json={"super_agent_id": sa_id},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["id"].startswith("psa-")
        assert body["template_sa_id"] == sa_id

    @patch("app.services.instance_service.InstanceService._create_worktree_for_instance")
    @patch("app.services.instance_service.InstanceService._create_initial_session")
    def test_create_team_instances(self, mock_session, mock_worktree, client, isolated_db):
        """POST with team_id creates team and SA instances and returns 201."""
        mock_worktree.return_value = None
        mock_session.return_value = None

        proj_id = create_project(name="Team Project")
        team_id = create_team(name="Test Team")
        sa_id = create_super_agent(name="Team SA", backend_type="claude")

        # Add SA as team member
        from app.db.teams import add_team_member

        add_team_member(team_id, super_agent_id=sa_id)

        resp = client.post(
            f"/admin/projects/{proj_id}/instances",
            json={"team_id": team_id},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert "team_instance_id" in body
        assert body["team_instance_id"].startswith("pti-")
        assert isinstance(body["sa_instances"], list)

    def test_create_instance_project_not_found(self, client, isolated_db):
        """POST to non-existent project returns 404."""
        resp = client.post(
            "/admin/projects/proj-nonexistent/instances",
            json={"super_agent_id": "sa-fake"},
        )
        assert resp.status_code == 404

    def test_create_instance_no_body(self, client, isolated_db):
        """POST without JSON body returns 400."""
        proj_id = create_project(name="No Body Project")
        resp = client.post(
            f"/admin/projects/{proj_id}/instances",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_create_instance_missing_ids(self, client, isolated_db):
        """POST without team_id or super_agent_id returns 400."""
        proj_id = create_project(name="Missing IDs Project")
        resp = client.post(
            f"/admin/projects/{proj_id}/instances",
            json={"description": "no ids"},
        )
        assert resp.status_code == 400

    @patch("app.services.instance_service.InstanceService._create_worktree_for_instance")
    @patch("app.services.instance_service.InstanceService._create_initial_session")
    def test_create_sa_instance_nonexistent_sa(
        self, mock_session, mock_worktree, client, isolated_db
    ):
        """POST with nonexistent super_agent_id returns 400."""
        mock_worktree.return_value = None
        mock_session.return_value = None

        proj_id = create_project(name="Bad SA Project")
        resp = client.post(
            f"/admin/projects/{proj_id}/instances",
            json={"super_agent_id": "sa-nonexistent"},
        )
        assert resp.status_code == 400


# =============================================================================
# GET /<project_id>/instances — List instances
# =============================================================================


class TestListInstances:
    def test_list_instances_empty(self, client, isolated_db):
        """GET returns empty list when project has no instances."""
        proj_id = create_project(name="Empty Project")
        resp = client.get(f"/admin/projects/{proj_id}/instances")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["instances"] == []

    def test_list_instances_populated(self, client, isolated_db):
        """GET returns instances with template SA info."""
        proj_id, sa_id = _setup_project_and_sa(isolated_db)
        create_project_sa_instance(proj_id, sa_id)

        resp = client.get(f"/admin/projects/{proj_id}/instances")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["instances"]) == 1
        inst = body["instances"][0]
        assert inst["template_sa_id"] == sa_id
        assert inst["sa_name"] == "Test SA"
        assert inst["sa_backend_type"] == "claude"

    def test_list_instances_multiple(self, client, isolated_db):
        """GET returns multiple instances for a project."""
        proj_id = create_project(name="Multi Instance Project")
        sa_id1 = create_super_agent(name="SA One", backend_type="claude")
        sa_id2 = create_super_agent(name="SA Two", backend_type="claude")
        create_project_sa_instance(proj_id, sa_id1)
        create_project_sa_instance(proj_id, sa_id2)

        resp = client.get(f"/admin/projects/{proj_id}/instances")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["instances"]) == 2


# =============================================================================
# GET /<project_id>/instances/<instance_id> — Instance detail
# =============================================================================


class TestGetInstance:
    def test_get_instance(self, client, isolated_db):
        """GET returns instance with SA info and sessions."""
        proj_id, sa_id = _setup_project_and_sa(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)

        resp = client.get(f"/admin/projects/{proj_id}/instances/{psa_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == psa_id
        assert body["project_id"] == proj_id
        assert body["template_sa_id"] == sa_id
        assert body["sa_name"] == "Test SA"
        assert "sessions" in body
        assert isinstance(body["sessions"], list)

    def test_get_instance_not_found(self, client, isolated_db):
        """GET returns 404 for non-existent instance."""
        proj_id = create_project(name="No Instance Project")
        resp = client.get(f"/admin/projects/{proj_id}/instances/psa-nonexist")
        assert resp.status_code == 404

    def test_get_instance_wrong_project(self, client, isolated_db):
        """GET returns 404 when instance belongs to different project."""
        proj_id1 = create_project(name="Project A")
        proj_id2 = create_project(name="Project B")
        sa_id = create_super_agent(name="SA X", backend_type="claude")
        psa_id = create_project_sa_instance(proj_id1, sa_id)

        resp = client.get(f"/admin/projects/{proj_id2}/instances/{psa_id}")
        assert resp.status_code == 404


# =============================================================================
# DELETE /<project_id>/instances/<instance_id> — Delete instance
# =============================================================================


class TestDeleteInstance:
    @patch("app.services.instance_service.InstanceService._remove_worktree")
    def test_delete_instance(self, mock_remove, client, isolated_db):
        """DELETE removes instance and returns 200."""
        mock_remove.return_value = True

        proj_id, sa_id = _setup_project_and_sa(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)

        resp = client.delete(f"/admin/projects/{proj_id}/instances/{psa_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Instance deleted"

        # Verify it's gone
        assert get_project_sa_instance(psa_id) is None

    def test_delete_instance_not_found(self, client, isolated_db):
        """DELETE returns 404 for non-existent instance."""
        proj_id = create_project(name="Del Project")
        resp = client.delete(f"/admin/projects/{proj_id}/instances/psa-nonexist")
        assert resp.status_code == 404

    def test_delete_instance_wrong_project(self, client, isolated_db):
        """DELETE returns 404 when instance belongs to different project."""
        proj_id1 = create_project(name="Project X")
        proj_id2 = create_project(name="Project Y")
        sa_id = create_super_agent(name="SA Y", backend_type="claude")
        psa_id = create_project_sa_instance(proj_id1, sa_id)

        resp = client.delete(f"/admin/projects/{proj_id2}/instances/{psa_id}")
        assert resp.status_code == 404

        # Instance should still exist
        assert get_project_sa_instance(psa_id) is not None
