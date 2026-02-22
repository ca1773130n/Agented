"""Tests for trigger-to-team integration: execution_mode, team_id, and dispatch delegation."""

from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_team(isolated_db, team_id="team-test01"):
    """Create a team directly in the DB and return its ID."""
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO teams (id, name, enabled) VALUES (?, ?, 1)",
            (team_id, "Test Team"),
        )
        conn.commit()
    return team_id


def _create_trigger_with_mode(
    isolated_db,
    trigger_source="webhook",
    execution_mode="direct",
    team_id=None,
    match_field_path=None,
    match_field_value=None,
):
    """Create a trigger with execution_mode and team_id set."""
    from app.database import add_trigger, get_trigger

    trigger_id = add_trigger(
        name="Test Trigger",
        prompt_template="test {message}",
        backend_type="claude",
        trigger_source=trigger_source,
        execution_mode=execution_mode,
        team_id=team_id,
        match_field_path=match_field_path,
        match_field_value=match_field_value,
    )
    assert trigger_id is not None
    trigger = get_trigger(trigger_id)
    assert trigger is not None
    return trigger


# ---------------------------------------------------------------------------
# Test 1: Create trigger with team_id
# ---------------------------------------------------------------------------


def test_trigger_creation_with_team_id(isolated_db):
    """Create a trigger with execution_mode='team' and team_id, verify stored correctly."""
    team_id = _create_team(isolated_db)
    trigger = _create_trigger_with_mode(isolated_db, execution_mode="team", team_id=team_id)

    assert trigger["execution_mode"] == "team"
    assert trigger["team_id"] == team_id


# ---------------------------------------------------------------------------
# Test 2: Update trigger execution_mode
# ---------------------------------------------------------------------------


def test_trigger_update_execution_mode(isolated_db):
    """Update existing trigger to set execution_mode='team' and team_id, verify."""
    from app.database import get_trigger, update_trigger

    team_id = _create_team(isolated_db)
    trigger = _create_trigger_with_mode(isolated_db)

    assert trigger["execution_mode"] == "direct"
    assert trigger["team_id"] is None

    success = update_trigger(trigger["id"], execution_mode="team", team_id=team_id)
    assert success is True

    updated = get_trigger(trigger["id"])
    assert updated["execution_mode"] == "team"
    assert updated["team_id"] == team_id


# ---------------------------------------------------------------------------
# Test 3: Default execution_mode
# ---------------------------------------------------------------------------


def test_trigger_default_execution_mode(isolated_db):
    """New triggers have execution_mode='direct' by default."""
    from app.database import add_trigger, get_trigger

    trigger_id = add_trigger(
        name="Default Mode Trigger",
        prompt_template="test",
    )
    trigger = get_trigger(trigger_id)

    assert trigger["execution_mode"] == "direct"
    assert trigger["team_id"] is None


# ---------------------------------------------------------------------------
# Test 4: Webhook dispatch delegates to team
# ---------------------------------------------------------------------------


def test_webhook_dispatch_delegates_to_team(isolated_db):
    """Mock TeamExecutionService.execute_team, verify delegation for team-mode trigger."""
    team_id = _create_team(isolated_db)
    _create_trigger_with_mode(
        isolated_db,
        trigger_source="webhook",
        execution_mode="team",
        team_id=team_id,
        match_field_path="event.type",
        match_field_value="test",
    )

    with (
        patch(
            "app.services.team_execution_service.TeamExecutionService.execute_team"
        ) as mock_execute_team,
        patch(
            "app.services.orchestration_service.OrchestrationService.execute_with_fallback"
        ) as mock_orchestration,
    ):
        mock_execute_team.return_value = "team-exec-test"

        from app.services.execution_service import ExecutionService

        triggered = ExecutionService.dispatch_webhook_event(
            {"event": {"type": "test", "text": "hello world"}}
        )

    assert triggered is True
    mock_execute_team.assert_called_once()
    call_args = mock_execute_team.call_args
    assert call_args[0][0] == team_id  # team_id
    assert call_args[0][3] == "webhook"  # trigger_type
    # OrchestrationService should NOT have been called for this trigger
    mock_orchestration.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: Direct mode unchanged
# ---------------------------------------------------------------------------


def test_webhook_dispatch_direct_mode_unchanged(isolated_db):
    """Trigger with execution_mode='direct' still goes through OrchestrationService."""
    _create_trigger_with_mode(
        isolated_db,
        trigger_source="webhook",
        execution_mode="direct",
        match_field_path="event.type",
        match_field_value="test",
    )

    with (
        patch(
            "app.services.team_execution_service.TeamExecutionService.execute_team"
        ) as mock_execute_team,
        patch(
            "app.services.orchestration_service.OrchestrationService.execute_with_fallback"
        ) as mock_orchestration,
    ):
        from app.services.execution_service import ExecutionService

        triggered = ExecutionService.dispatch_webhook_event(
            {"event": {"type": "test", "text": "hello world"}}
        )

    assert triggered is True
    mock_execute_team.assert_not_called()
    mock_orchestration.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: GitHub dispatch delegates to team
# ---------------------------------------------------------------------------


def test_github_dispatch_delegates_to_team(isolated_db):
    """Verify dispatch_github_event delegates to team for team-mode triggers."""
    team_id = _create_team(isolated_db)
    _create_trigger_with_mode(
        isolated_db,
        trigger_source="github",
        execution_mode="team",
        team_id=team_id,
    )

    with (
        patch(
            "app.services.team_execution_service.TeamExecutionService.execute_team"
        ) as mock_execute_team,
        patch(
            "app.services.orchestration_service.OrchestrationService.execute_with_fallback"
        ) as mock_orchestration,
    ):
        mock_execute_team.return_value = "team-exec-github"

        from app.services.execution_service import ExecutionService

        triggered = ExecutionService.dispatch_github_event(
            repo_url="https://github.com/test/repo",
            pr_data={
                "pr_number": 42,
                "pr_title": "Test PR",
                "pr_url": "https://github.com/test/repo/pull/42",
                "pr_author": "testuser",
                "repo_full_name": "test/repo",
                "action": "opened",
            },
        )

    assert triggered is True
    # TeamExecutionService should be called for the team-mode trigger
    mock_execute_team.assert_called_once()
    call_args = mock_execute_team.call_args
    assert call_args[0][0] == team_id
    assert call_args[0][3] == "github_webhook"
    # OrchestrationService is called for the predefined bot-pr-review (direct mode),
    # but NOT for our team-mode test trigger. Verify only 1 orchestration call
    # (the predefined trigger) -- our test trigger should have been delegated to team.
    assert mock_orchestration.call_count == 1
    # Verify the orchestration call was for the predefined trigger, not our test trigger
    orch_trigger = mock_orchestration.call_args[0][0]
    assert orch_trigger["id"] == "bot-pr-review"
