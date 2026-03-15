"""Tests for project-scoped sketch routing."""

from app.db import get_connection, init_db
from app.db.bundle_seeds import seed_bundled_teams_and_agents
from app.services.sketch_routing_service import SketchRoutingService


def _create_project(conn, project_id="proj-test", name="Test Project"):
    """Create a test project."""
    conn.execute(
        "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
        (project_id, name),
    )
    conn.commit()
    return project_id


def _assign_team_to_project(conn, project_id, team_id):
    """Link a team to a project."""
    conn.execute(
        "INSERT OR IGNORE INTO project_teams (project_id, team_id) VALUES (?, ?)",
        (project_id, team_id),
    )
    conn.commit()


class TestProjectScopedRouting:
    """Test routing scoped to a project's teams."""

    def test_route_without_project_id_searches_globally(self, client):
        """Backward compatible — no project_id does global search."""
        seed_bundled_teams_and_agents()
        classification = {"phase": "research", "domains": ["papers"], "complexity": "medium"}
        result = SketchRoutingService.route(classification)
        # Should find a match globally (Neo or Seraph have 'research' in description)
        assert result["target_type"] != "none"

    def test_route_with_project_id_scopes_to_project_teams(self, client):
        """Only teams assigned to the project are searched."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-dev")
            # Only assign development team
            _assign_team_to_project(conn, "proj-dev", "team-mx-development")

        classification = {"phase": "execution", "domains": ["backend"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-dev")
        # Should match development team or its members
        assert result["target_type"] in ("team", "super_agent")

    def test_route_with_project_id_returns_none_for_unassigned_domain(self, client):
        """Research prompt to a project with only dev team returns none."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-dev-only")
            _assign_team_to_project(conn, "proj-dev-only", "team-mx-development")

        classification = {"phase": "research", "domains": ["papers"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-dev-only")
        assert result["target_type"] == "none"

    def test_route_with_nonexistent_project_returns_none(self, client):
        """Project with no teams returns none."""
        classification = {"phase": "execution", "domains": ["backend"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-nonexistent")
        assert result["target_type"] == "none"
