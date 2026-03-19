"""Tests for instance-aware sketch routing and execution.

Verifies that when a sketch belongs to a project with SA instances (psa-),
the routing service resolves to instance IDs and the execution service
uses the correct template SA, cwd, and chat_mode.
"""

from unittest.mock import patch

from app.db import get_connection
from app.db.bundle_seeds import seed_bundled_teams_and_agents
from app.db.project_sa_instances import create_project_sa_instance
from app.services.sketch_execution_service import execute_sketch
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


class TestInstanceAwareRouting:
    """Test routing resolves to psa- instances when a project has them."""

    def test_route_resolves_sa_to_psa_instance(self, client):
        """When project has a psa- instance matching the resolved SA, use it."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-inst")
            _assign_team_to_project(conn, "proj-inst", "team-mx-research")

        # Create a project SA instance for Neo (research leader)
        psa_id = create_project_sa_instance(
            project_id="proj-inst",
            template_sa_id="sa-neo",
            worktree_path="/tmp/worktree/proj-inst",
        )

        classification = {"phase": "research", "domains": ["papers"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-inst")

        assert result["target_type"] == "super_agent"
        assert result["target_id"] == psa_id
        assert "routed to project instance" in result["reason"]

    def test_route_without_instance_keeps_global_sa(self, client):
        """When project has no psa- instances, routing returns global SA ID."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-noinst")
            _assign_team_to_project(conn, "proj-noinst", "team-mx-research")

        classification = {"phase": "research", "domains": ["papers"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-noinst")

        assert result["target_type"] == "super_agent"
        # Should be a global SA ID (sa- prefix, not psa-)
        assert result["target_id"].startswith("sa-")

    def test_route_team_to_psa_instance_via_leader(self, client):
        """When team routing resolves and leader has a psa- instance, swap to it."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-team-inst")
            _assign_team_to_project(conn, "proj-team-inst", "team-mx-development")

        # Create instance for Trinity (development leader)
        psa_id = create_project_sa_instance(
            project_id="proj-team-inst",
            template_sa_id="sa-trinity",
            worktree_path="/tmp/worktree/proj-team-inst",
        )

        classification = {"phase": "execution", "domains": ["backend"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-team-inst")

        # Should resolve to psa- instance, not team or raw SA
        assert result["target_type"] == "super_agent"
        assert result["target_id"] == psa_id
        assert "routed to project instance" in result["reason"]

    def test_route_no_teams_but_has_instances_uses_instance(self, client):
        """Project with no teams but SA instances still routes to an instance."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-only-inst")

        psa_id = create_project_sa_instance(
            project_id="proj-only-inst",
            template_sa_id="sa-trinity",
            worktree_path="/tmp/worktree/proj-only-inst",
        )

        classification = {"phase": "execution", "domains": ["backend"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-only-inst")

        assert result["target_type"] == "super_agent"
        assert result["target_id"] == psa_id

    def test_route_picks_best_instance_by_domain(self, client):
        """With multiple instances, prefer the one matching classified domains."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-multi")

        # Neo's description: "Lead Researcher"
        create_project_sa_instance(
            project_id="proj-multi",
            template_sa_id="sa-neo",
            worktree_path="/tmp/worktree/neo",
        )
        # Apoc's description: "Backend Engineer — APIs, database, server logic"
        psa_apoc = create_project_sa_instance(
            project_id="proj-multi",
            template_sa_id="sa-apoc",
            worktree_path="/tmp/worktree/apoc",
        )

        # Classify as backend domain — should prefer Apoc
        classification = {"phase": "execution", "domains": ["backend"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-multi")

        assert result["target_type"] == "super_agent"
        assert result["target_id"] == psa_apoc

    def test_route_without_project_id_ignores_instances(self, client):
        """Global routing (no project_id) does not use psa- instances."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-global")

        create_project_sa_instance(
            project_id="proj-global",
            template_sa_id="sa-neo",
            worktree_path="/tmp/worktree/global",
        )

        classification = {"phase": "research", "domains": ["papers"], "complexity": "medium"}
        result = SketchRoutingService.route(classification)

        # Should be a global SA (not psa-)
        assert result["target_type"] != "none"
        assert not result["target_id"].startswith("psa-")


class TestResolveToInstance:
    """Test _resolve_to_instance helper directly."""

    def test_no_instances_returns_original(self, client):
        """With empty psa_instances list, result is unchanged."""
        result = {
            "target_type": "super_agent",
            "target_id": "sa-trinity",
            "reason": "Test",
        }
        out = SketchRoutingService._resolve_to_instance(result, [], [])
        assert out["target_id"] == "sa-trinity"
        assert out["target_type"] == "super_agent"

    def test_matching_instance_swaps_id(self, client):
        """Instance with matching template_sa_id swaps target_id."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-resolve")

        psa_id = create_project_sa_instance(
            project_id="proj-resolve",
            template_sa_id="sa-trinity",
        )

        from app.db.project_sa_instances import get_project_sa_instances_for_project

        instances = get_project_sa_instances_for_project("proj-resolve")

        result = {
            "target_type": "super_agent",
            "target_id": "sa-trinity",
            "reason": "Test",
        }
        out = SketchRoutingService._resolve_to_instance(result, instances, [])
        assert out["target_id"] == psa_id
        assert out["target_type"] == "super_agent"


class TestPickBestInstance:
    """Test _pick_best_instance helper."""

    def test_empty_instances_returns_none(self, client):
        """Empty list returns None."""
        assert SketchRoutingService._pick_best_instance([], ["backend"]) is None

    def test_no_domains_returns_first(self, client):
        """With no domains, returns the first instance."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-pick")

        create_project_sa_instance(project_id="proj-pick", template_sa_id="sa-neo")
        create_project_sa_instance(project_id="proj-pick", template_sa_id="sa-trinity")

        from app.db.project_sa_instances import get_project_sa_instances_for_project

        instances = get_project_sa_instances_for_project("proj-pick")
        best = SketchRoutingService._pick_best_instance(instances, [])
        assert best is not None
        assert best["id"] == instances[0]["id"]


class TestInstanceAwareExecution:
    """Test execute_sketch handles psa- IDs correctly."""

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_psa_id_resolves_template_and_cwd(self, mock_stream, client):
        """When super_agent_id starts with psa-, execution uses template SA and cwd."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-exec")
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-psa1', 'Test PSA', 'Build feature', 'routed')"
            )
            conn.commit()

        psa_id = create_project_sa_instance(
            project_id="proj-exec",
            template_sa_id="sa-trinity",
            worktree_path="/tmp/worktree/exec-test",
        )

        session_id = execute_sketch("sk-psa1", psa_id, "Build feature")

        assert session_id is not None
        mock_stream.assert_called_once()
        call_kwargs = mock_stream.call_args.kwargs

        # Should use template SA ID, not psa- ID
        assert call_kwargs["super_agent_id"] == "sa-trinity"
        # Should pass worktree_path as cwd
        assert call_kwargs["cwd"] == "/tmp/worktree/exec-test"
        # Should set chat_mode to "work" when cwd is present
        assert call_kwargs["chat_mode"] == "work"
        # Should pass instance_id
        assert call_kwargs["instance_id"] == psa_id
        # Backend should be resolved from template SA
        assert call_kwargs["backend"] == "claude"

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_psa_id_without_worktree_no_cwd(self, mock_stream, client):
        """When psa- instance has no worktree_path, cwd and chat_mode are None."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-exec2")
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-psa2', 'Test PSA No CWD', 'Research topic', 'routed')"
            )
            conn.commit()

        psa_id = create_project_sa_instance(
            project_id="proj-exec2",
            template_sa_id="sa-neo",
            # No worktree_path
        )

        execute_sketch("sk-psa2", psa_id, "Research topic")

        call_kwargs = mock_stream.call_args.kwargs
        assert call_kwargs["super_agent_id"] == "sa-neo"
        assert call_kwargs["cwd"] is None
        assert call_kwargs["chat_mode"] is None

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_regular_sa_id_no_cwd(self, mock_stream, client):
        """Regular sa- ID execution has no cwd or instance_id."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-reg', 'Regular', 'Hello', 'routed')"
            )
            conn.commit()

        execute_sketch("sk-reg", "sa-trinity", "Hello")

        call_kwargs = mock_stream.call_args.kwargs
        assert call_kwargs["super_agent_id"] == "sa-trinity"
        assert call_kwargs["cwd"] is None
        assert call_kwargs["chat_mode"] is None
        assert call_kwargs["instance_id"] is None

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_psa_status_set_to_in_progress(self, mock_stream, client):
        """Sketch status is set to in_progress for psa- execution."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-exec3")
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-psa3', 'PSA Status', 'Work', 'routed')"
            )
            conn.commit()

        psa_id = create_project_sa_instance(
            project_id="proj-exec3",
            template_sa_id="sa-trinity",
            worktree_path="/tmp/worktree/status-test",
        )

        execute_sketch("sk-psa3", psa_id, "Work")

        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-psa3'").fetchone()
        assert sketch["status"] == "in_progress"
