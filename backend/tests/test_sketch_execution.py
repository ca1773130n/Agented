"""Tests for sketch execution service."""

from unittest.mock import patch, MagicMock

from app.db import get_connection
from app.db.bundle_seeds import seed_bundled_teams_and_agents
from app.services.sketch_execution_service import execute_sketch, find_team_super_agent


class TestFindTeamSuperAgent:
    """Test team → super agent resolution."""

    def test_finds_leader(self, client):
        """Returns leader super agent for a team."""
        seed_bundled_teams_and_agents()
        result = find_team_super_agent("team-mx-development")
        assert result == "sa-trinity"

    def test_finds_leader_for_research_team(self, client):
        """Returns Neo as leader of research team."""
        seed_bundled_teams_and_agents()
        result = find_team_super_agent("team-mx-research")
        assert result == "sa-neo"

    def test_returns_none_for_nonexistent_team(self, client):
        """Returns None for a team that doesn't exist."""
        result = find_team_super_agent("team-nonexistent")
        assert result is None

    def test_returns_none_for_team_without_super_agents(self, client):
        """Returns None for a team with no super agent members."""
        with get_connection() as conn:
            conn.execute("INSERT INTO teams (id, name) VALUES ('team-empty', 'Empty Team')")
            conn.commit()
        result = find_team_super_agent("team-empty")
        assert result is None


class TestExecuteSketch:
    """Test sketch execution flow."""

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_execute_sketch_sets_in_progress(self, mock_stream, client):
        """Status is set to in_progress before streaming starts."""
        seed_bundled_teams_and_agents()
        # Create a test sketch
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-test', 'Test', 'Hello', 'routed')"
            )
            conn.commit()

        session_id = execute_sketch("sk-test", "sa-trinity", "Hello")

        assert session_id is not None
        # Verify status was set to in_progress
        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-test'").fetchone()
        assert sketch["status"] == "in_progress"

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_execute_sketch_calls_streaming(self, mock_stream, client):
        """Streaming helper is called with correct args."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-test2', 'Test', 'Build an API', 'routed')"
            )
            conn.commit()

        execute_sketch("sk-test2", "sa-trinity", "Build an API")

        mock_stream.assert_called_once()
        call_kwargs = mock_stream.call_args
        assert call_kwargs.kwargs["super_agent_id"] == "sa-trinity"
        assert call_kwargs.kwargs["backend"] == "claude"
        assert call_kwargs.kwargs["on_complete"] is not None
        assert call_kwargs.kwargs["on_error"] is not None
