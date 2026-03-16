"""Tests for sketch execution service."""

import json
from unittest.mock import MagicMock, patch

from app.db import get_connection
from app.db.bundle_seeds import seed_bundled_teams_and_agents
from app.services.sketch_execution_service import (
    _check_all_delegations_complete,
    _mark_delegation_status,
    execute_delegate,
    execute_sketch,
    find_team_super_agent,
    get_team_context,
    process_delegations,
)


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


class TestGetTeamContext:
    """Test get_team_context function."""

    def test_returns_team_id_and_members(self, client):
        """Returns team_id and member list for a valid team."""
        seed_bundled_teams_and_agents()
        result = get_team_context("team-mx-development")
        assert result["team_id"] == "team-mx-development"
        assert isinstance(result["members"], list)
        assert len(result["members"]) > 0

    def test_member_fields_present(self, client):
        """Each member dict has required fields."""
        seed_bundled_teams_and_agents()
        result = get_team_context("team-mx-development")
        member = result["members"][0]
        assert "super_agent_id" in member
        assert "name" in member
        assert "role" in member
        assert "layer" in member
        assert "description" in member

    def test_leader_is_included(self, client):
        """Trinity (leader) is in the development team members."""
        seed_bundled_teams_and_agents()
        result = get_team_context("team-mx-development")
        member_ids = [m["super_agent_id"] for m in result["members"]]
        assert "sa-trinity" in member_ids

    def test_returns_empty_members_for_nonexistent_team(self, client):
        """Returns empty members list for a team with no super agents."""
        result = get_team_context("team-nonexistent")
        assert result["team_id"] == "team-nonexistent"
        assert result["members"] == []


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

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_execute_sketch_with_team_id_stores_team_in_routing(self, mock_stream, client):
        """When team_id provided, routing_json is updated with team_id and delegations."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-team', 'Team Sketch', 'Do work', 'routed')"
            )
            conn.commit()

        execute_sketch("sk-team", "sa-trinity", "Do work", team_id="team-mx-development")

        with get_connection() as conn:
            row = conn.execute(
                "SELECT routing_json, status FROM sketches WHERE id = 'sk-team'"
            ).fetchone()
        assert row["status"] == "in_progress"
        routing = json.loads(row["routing_json"])
        assert routing["team_id"] == "team-mx-development"
        assert "delegations" in routing

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_execute_sketch_with_team_prepends_context(self, mock_stream, client):
        """When team_id provided, team context preamble is prepended to content."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-team2', 'Team Sketch 2', 'Build feature', 'routed')"
            )
            conn.commit()

        with patch(
            "app.services.sketch_execution_service.SuperAgentSessionService.send_message"
        ) as mock_send:
            execute_sketch("sk-team2", "sa-trinity", "Build feature", team_id="team-mx-development")
            # The content sent should include team context preamble
            assert mock_send.called
            sent_content = mock_send.call_args[0][1]
            assert "[TEAM CONTEXT]" in sent_content
            assert "Build feature" in sent_content

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_on_complete_without_team_marks_completed(self, mock_stream, client):
        """on_complete callback marks sketch as completed when no team delegation."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-comp', 'Complete Test', 'Hello', 'routed')"
            )
            conn.commit()

        execute_sketch("sk-comp", "sa-trinity", "Hello")

        # Trigger the on_complete callback manually
        on_complete = mock_stream.call_args.kwargs["on_complete"]
        on_complete()

        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-comp'").fetchone()
        assert sketch["status"] == "completed"

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_on_error_resets_to_classified(self, mock_stream, client):
        """on_error callback resets sketch status to classified."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-err', 'Error Test', 'Hello', 'routed')"
            )
            conn.commit()

        execute_sketch("sk-err", "sa-trinity", "Hello")

        on_error = mock_stream.call_args.kwargs["on_error"]
        on_error("Something went wrong")

        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-err'").fetchone()
        assert sketch["status"] == "classified"


class TestProcessDelegations:
    """Test process_delegations function."""

    def _make_sketch(self, sketch_id, title="Test Sketch", content="Do the work"):
        """Insert a test sketch into the DB."""
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES (?, ?, ?, 'collaborating', ?)",
                (
                    sketch_id,
                    title,
                    content,
                    json.dumps({"team_id": "team-mx-development", "delegations": []}),
                ),
            )
            conn.commit()

    @patch("app.services.sketch_execution_service.execute_delegate")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_no_mentions_marks_sketch_completed(self, mock_send, mock_delegate, client):
        """When leader response has no @mentions, sketch is marked completed."""
        seed_bundled_teams_and_agents()
        self._make_sketch("sk-proc1")

        team_context = get_team_context("team-mx-development")
        process_delegations("sk-proc1", "sa-trinity", "No mentions here.", team_context)

        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-proc1'").fetchone()
        assert sketch["status"] == "completed"
        mock_delegate.assert_not_called()

    @patch("app.services.sketch_execution_service.execute_delegate")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_mention_matches_member_sends_mailbox(self, mock_send, mock_delegate, client):
        """@Apoc mention sends mailbox message to Apoc."""
        seed_bundled_teams_and_agents()
        self._make_sketch("sk-proc2")

        team_context = get_team_context("team-mx-development")
        leader_response = "@Apoc - Build the REST API endpoints for users."
        process_delegations("sk-proc2", "sa-trinity", leader_response, team_context)

        assert mock_send.called
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["from_agent_id"] == "sa-trinity"
        assert call_kwargs["to_agent_id"] == "sa-apoc"
        assert call_kwargs["message_type"] == "request"
        assert call_kwargs["priority"] == "high"

    @patch("app.services.sketch_execution_service.execute_delegate")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_mention_launches_delegate(self, mock_send, mock_delegate, client):
        """@Switch mention launches execute_delegate for Switch."""
        seed_bundled_teams_and_agents()
        self._make_sketch("sk-proc3")

        team_context = get_team_context("team-mx-development")
        leader_response = "@Switch - Build the frontend dashboard component."
        process_delegations("sk-proc3", "sa-trinity", leader_response, team_context)

        mock_delegate.assert_called_once()
        kwargs = mock_delegate.call_args.kwargs
        assert kwargs["super_agent_id"] == "sa-switch"
        assert kwargs["sketch_id"] == "sk-proc3"
        assert kwargs["leader_agent_id"] == "sa-trinity"

    @patch("app.services.sketch_execution_service.execute_delegate")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_multiple_mentions_launch_multiple_delegates(self, mock_send, mock_delegate, client):
        """Multiple @mentions launch one delegate per matched member."""
        seed_bundled_teams_and_agents()
        self._make_sketch("sk-proc4")

        team_context = get_team_context("team-mx-development")
        leader_response = "@Apoc - Build the backend API.\n@Switch - Build the frontend UI."
        process_delegations("sk-proc4", "sa-trinity", leader_response, team_context)

        assert mock_delegate.call_count == 2

    @patch("app.services.sketch_execution_service.execute_delegate")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_unmatched_mention_is_skipped(self, mock_send, mock_delegate, client):
        """@Unknown mention that doesn't match any team member is skipped."""
        seed_bundled_teams_and_agents()
        self._make_sketch("sk-proc5")

        team_context = get_team_context("team-mx-development")
        leader_response = "@Unknown - Do something."
        process_delegations("sk-proc5", "sa-trinity", leader_response, team_context)

        mock_delegate.assert_not_called()
        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-proc5'").fetchone()
        assert sketch["status"] == "completed"

    @patch("app.services.sketch_execution_service.execute_delegate")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_sets_sketch_to_collaborating(self, mock_send, mock_delegate, client):
        """Sketch status is set to 'collaborating' when valid mentions are found."""
        seed_bundled_teams_and_agents()
        self._make_sketch("sk-proc6")
        # Start from in_progress
        with get_connection() as conn:
            conn.execute("UPDATE sketches SET status = 'in_progress' WHERE id = 'sk-proc6'")
            conn.commit()

        team_context = get_team_context("team-mx-development")
        leader_response = "@Apoc - Build the database schema."
        process_delegations("sk-proc6", "sa-trinity", leader_response, team_context)

        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-proc6'").fetchone()
        assert sketch["status"] == "collaborating"

    @patch("app.services.sketch_execution_service.execute_delegate")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_delegations_stored_in_routing_json(self, mock_send, mock_delegate, client):
        """Delegation info is stored in routing_json."""
        seed_bundled_teams_and_agents()
        self._make_sketch("sk-proc7")

        team_context = get_team_context("team-mx-development")
        leader_response = "@Apoc - Set up the REST API."
        process_delegations("sk-proc7", "sa-trinity", leader_response, team_context)

        with get_connection() as conn:
            row = conn.execute("SELECT routing_json FROM sketches WHERE id = 'sk-proc7'").fetchone()
        routing = json.loads(row["routing_json"])
        assert len(routing["delegations"]) == 1
        assert routing["delegations"][0]["super_agent_id"] == "sa-apoc"
        assert routing["delegations"][0]["status"] == "pending"


class TestMarkDelegationStatus:
    """Test _mark_delegation_status helper."""

    def test_updates_delegation_status(self, client):
        """Delegation status is updated in routing_json."""
        seed_bundled_teams_and_agents()
        routing = {
            "team_id": "team-mx-development",
            "delegations": [
                {
                    "super_agent_id": "sa-apoc",
                    "name": "Apoc",
                    "task": "Build API",
                    "status": "pending",
                },
            ],
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES ('sk-mark', 'Test', 'content', 'collaborating', ?)",
                (json.dumps(routing),),
            )
            conn.commit()

        _mark_delegation_status("sk-mark", "sa-apoc", "completed")

        with get_connection() as conn:
            row = conn.execute("SELECT routing_json FROM sketches WHERE id = 'sk-mark'").fetchone()
        updated = json.loads(row["routing_json"])
        assert updated["delegations"][0]["status"] == "completed"


class TestCheckAllDelegationsComplete:
    """Test _check_all_delegations_complete helper."""

    def test_marks_completed_when_all_done(self, client):
        """Sketch is marked 'completed' when all delegations are done."""
        seed_bundled_teams_and_agents()
        routing = {
            "delegations": [
                {"super_agent_id": "sa-apoc", "status": "completed"},
                {"super_agent_id": "sa-switch", "status": "completed"},
            ]
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES ('sk-chk1', 'Test', 'content', 'collaborating', ?)",
                (json.dumps(routing),),
            )
            conn.commit()

        _check_all_delegations_complete("sk-chk1")

        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-chk1'").fetchone()
        assert sketch["status"] == "completed"

    def test_stays_collaborating_when_pending_exists(self, client):
        """Sketch stays 'collaborating' while a delegation is still pending."""
        seed_bundled_teams_and_agents()
        routing = {
            "delegations": [
                {"super_agent_id": "sa-apoc", "status": "completed"},
                {"super_agent_id": "sa-switch", "status": "pending"},
            ]
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES ('sk-chk2', 'Test', 'content', 'collaborating', ?)",
                (json.dumps(routing),),
            )
            conn.commit()

        _check_all_delegations_complete("sk-chk2")

        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-chk2'").fetchone()
        assert sketch["status"] == "collaborating"

    def test_marks_completed_when_all_errored(self, client):
        """Sketch is marked 'completed' even when all delegations errored."""
        seed_bundled_teams_and_agents()
        routing = {
            "delegations": [
                {"super_agent_id": "sa-apoc", "status": "error"},
            ]
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES ('sk-chk3', 'Test', 'content', 'collaborating', ?)",
                (json.dumps(routing),),
            )
            conn.commit()

        _check_all_delegations_complete("sk-chk3")

        with get_connection() as conn:
            sketch = conn.execute("SELECT status FROM sketches WHERE id = 'sk-chk3'").fetchone()
        assert sketch["status"] == "completed"


class TestExecuteDelegate:
    """Test execute_delegate function."""

    @patch("app.services.sketch_execution_service.run_streaming_response")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_launches_streaming_for_delegate(self, mock_send, mock_stream, client):
        """Streaming is launched for the delegate agent."""
        seed_bundled_teams_and_agents()
        routing = {
            "team_id": "team-mx-development",
            "delegations": [
                {
                    "super_agent_id": "sa-apoc",
                    "name": "Apoc",
                    "task": "Build API",
                    "status": "pending",
                },
            ],
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES ('sk-del1', 'Test', 'Build an app', 'collaborating', ?)",
                (json.dumps(routing),),
            )
            conn.commit()

        execute_delegate(
            sketch_id="sk-del1",
            super_agent_id="sa-apoc",
            task_content="Build the REST API",
            leader_agent_id="sa-trinity",
            sketch_content="Build an app",
            sketch_title="Test",
        )

        mock_stream.assert_called_once()
        call_kwargs = mock_stream.call_args.kwargs
        assert call_kwargs["super_agent_id"] == "sa-apoc"
        assert call_kwargs["backend"] == "claude"

    @patch("app.services.sketch_execution_service.run_streaming_response")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_delegate_prompt_includes_task_and_original(self, mock_send, mock_stream, client):
        """The delegate receives a prompt with both the original sketch and their task."""
        seed_bundled_teams_and_agents()
        routing = {
            "team_id": "team-mx-development",
            "delegations": [
                {
                    "super_agent_id": "sa-apoc",
                    "name": "Apoc",
                    "task": "Build API",
                    "status": "pending",
                },
            ],
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES ('sk-del2', 'Test', 'Build an app', 'collaborating', ?)",
                (json.dumps(routing),),
            )
            conn.commit()

        with patch(
            "app.services.sketch_execution_service.SuperAgentSessionService.send_message"
        ) as mock_session_send:
            execute_delegate(
                sketch_id="sk-del2",
                super_agent_id="sa-apoc",
                task_content="Build the REST API",
                leader_agent_id="sa-trinity",
                sketch_content="Build an app",
                sketch_title="Test",
            )
            assert mock_session_send.called
            sent_content = mock_session_send.call_args[0][1]
            assert "[DELEGATION FROM TEAM LEADER]" in sent_content
            assert "Build an app" in sent_content
            assert "Build the REST API" in sent_content

    @patch("app.services.sketch_execution_service.run_streaming_response")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_on_complete_sends_response_to_leader(self, mock_send, mock_stream, client):
        """Completion callback sends delegate's response back to the leader."""
        seed_bundled_teams_and_agents()
        routing = {
            "team_id": "team-mx-development",
            "delegations": [
                {
                    "super_agent_id": "sa-apoc",
                    "name": "Apoc",
                    "task": "Build API",
                    "status": "pending",
                },
            ],
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES ('sk-del3', 'Test', 'Build an app', 'collaborating', ?)",
                (json.dumps(routing),),
            )
            conn.commit()

        # Mock session state to return a response
        mock_state = {
            "conversation_log": [{"role": "assistant", "content": "Here is the API I built."}]
        }
        with patch(
            "app.services.sketch_execution_service.SuperAgentSessionService.get_session_state",
            return_value=mock_state,
        ):
            execute_delegate(
                sketch_id="sk-del3",
                super_agent_id="sa-apoc",
                task_content="Build the REST API",
                leader_agent_id="sa-trinity",
                sketch_content="Build an app",
                sketch_title="Test",
            )
            # Trigger the completion callback
            on_complete = mock_stream.call_args.kwargs["on_complete"]
            on_complete()

        # Verify mailbox was called to send back to leader
        assert mock_send.called
        reply_call = mock_send.call_args
        assert reply_call.kwargs["from_agent_id"] == "sa-apoc"
        assert reply_call.kwargs["to_agent_id"] == "sa-trinity"
        assert "Here is the API I built." in reply_call.kwargs["content"]

    @patch("app.services.sketch_execution_service.run_streaming_response")
    @patch("app.services.sketch_execution_service.AgentMessageBusService.send_message")
    def test_on_complete_marks_delegation_completed(self, mock_send, mock_stream, client):
        """Completion callback marks the delegation status as 'completed'."""
        seed_bundled_teams_and_agents()
        routing = {
            "team_id": "team-mx-development",
            "delegations": [
                {
                    "super_agent_id": "sa-apoc",
                    "name": "Apoc",
                    "task": "Build API",
                    "status": "pending",
                },
            ],
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status, routing_json) "
                "VALUES ('sk-del4', 'Test', 'Build an app', 'collaborating', ?)",
                (json.dumps(routing),),
            )
            conn.commit()

        mock_state = {"conversation_log": [{"role": "assistant", "content": "Done."}]}
        with patch(
            "app.services.sketch_execution_service.SuperAgentSessionService.get_session_state",
            return_value=mock_state,
        ):
            execute_delegate(
                sketch_id="sk-del4",
                super_agent_id="sa-apoc",
                task_content="Build the REST API",
                leader_agent_id="sa-trinity",
            )
            on_complete = mock_stream.call_args.kwargs["on_complete"]
            on_complete()

        with get_connection() as conn:
            row = conn.execute(
                "SELECT routing_json, status FROM sketches WHERE id = 'sk-del4'"
            ).fetchone()
        routing = json.loads(row["routing_json"])
        assert routing["delegations"][0]["status"] == "completed"
        # All done → sketch should be completed
        assert row["status"] == "completed"
