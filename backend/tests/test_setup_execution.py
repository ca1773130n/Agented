"""Tests for interactive plugin setup execution service and API routes."""

import json
import time

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_id(isolated_db):
    """Create a project and return its ID."""
    from app.database import add_project

    pid = add_project(name="Setup Test Project", local_path="/tmp/test-setup-project")
    return pid


# ---------------------------------------------------------------------------
# Test 1: Start setup creates DB record
# ---------------------------------------------------------------------------


def test_start_setup_creates_db_record(client, isolated_db, project_id, monkeypatch, tmp_path):
    """POST to /api/setup/start with a valid project_id creates execution and DB record."""
    # Mock workspace resolution to use tmp_path
    monkeypatch.setattr(
        "app.services.setup_execution_service.ProjectWorkspaceService.resolve_working_directory",
        lambda pid: str(tmp_path),
    )

    resp = client.post(
        "/api/setup/start",
        json={"project_id": project_id, "command": "echo hello"},
    )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    assert data["execution_id"].startswith("setup-")
    assert data["status"] == "running"

    # Allow background threads to start and process to complete
    time.sleep(0.5)

    # Verify DB record exists
    from app.database import get_setup_execution

    db_record = get_setup_execution(data["execution_id"])
    assert db_record is not None
    assert db_record["project_id"] == project_id
    assert db_record["command"] == "echo hello"


# ---------------------------------------------------------------------------
# Test 2: Setup status endpoint
# ---------------------------------------------------------------------------


def test_setup_status_endpoint(client, isolated_db, project_id, monkeypatch, tmp_path):
    """Start a setup and immediately GET status returns valid response."""
    monkeypatch.setattr(
        "app.services.setup_execution_service.ProjectWorkspaceService.resolve_working_directory",
        lambda pid: str(tmp_path),
    )

    # Start setup with a command that takes a moment
    resp = client.post(
        "/api/setup/start",
        json={"project_id": project_id, "command": "echo status_check"},
    )
    assert resp.status_code == 201
    execution_id = resp.get_json()["execution_id"]

    # Give it a brief moment
    time.sleep(0.3)

    # Get status
    resp = client.get(f"/api/setup/{execution_id}/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["execution_id"] == execution_id
    assert data["project_id"] == project_id
    assert data["status"] in ("running", "completed")
    assert data["command"] == "echo status_check"


# ---------------------------------------------------------------------------
# Test 3: Respond without pending interaction returns 404
# ---------------------------------------------------------------------------


def test_respond_without_pending_interaction_returns_404(
    client, isolated_db, project_id, monkeypatch, tmp_path
):
    """POST to /api/setup/{id}/respond with fake interaction_id returns 404."""
    monkeypatch.setattr(
        "app.services.setup_execution_service.ProjectWorkspaceService.resolve_working_directory",
        lambda pid: str(tmp_path),
    )

    # Start a simple setup
    resp = client.post(
        "/api/setup/start",
        json={"project_id": project_id, "command": "echo no_interaction"},
    )
    assert resp.status_code == 201
    execution_id = resp.get_json()["execution_id"]

    time.sleep(0.3)

    # Try to respond with a fake interaction_id
    resp = client.post(
        f"/api/setup/{execution_id}/respond",
        json={"interaction_id": "fake-interaction-id", "response": {"answer": "test"}},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 4: Cancel setup
# ---------------------------------------------------------------------------


def test_cancel_setup(client, isolated_db, project_id, monkeypatch, tmp_path):
    """Start a long-running setup and cancel it."""
    monkeypatch.setattr(
        "app.services.setup_execution_service.ProjectWorkspaceService.resolve_working_directory",
        lambda pid: str(tmp_path),
    )

    # Start a long-running command
    resp = client.post(
        "/api/setup/start",
        json={"project_id": project_id, "command": "sleep 60"},
    )
    assert resp.status_code == 201
    execution_id = resp.get_json()["execution_id"]

    time.sleep(0.3)

    # Cancel the setup
    resp = client.delete(f"/api/setup/{execution_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "Setup cancelled"

    time.sleep(0.3)

    # Verify DB shows cancelled
    from app.database import get_setup_execution

    db_record = get_setup_execution(execution_id)
    assert db_record is not None
    assert db_record["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Test 5: Parse interaction JSON tool_use
# ---------------------------------------------------------------------------


def test_try_parse_interaction_json_tool_use(isolated_db):
    """Direct unit test of _try_parse_interaction with JSON tool_use block."""
    from app.services.setup_execution_service import SetupExecutionService

    line = json.dumps(
        {
            "type": "tool_use",
            "name": "AskUserQuestion",
            "input": {"question": "Enter API key", "type": "password"},
        }
    )
    result = SetupExecutionService._try_parse_interaction(line)
    assert result is not None
    assert result["question_type"] == "password"
    assert "API key" in result["prompt"]


# ---------------------------------------------------------------------------
# Test 6: Parse interaction returns None for regular log
# ---------------------------------------------------------------------------


def test_try_parse_interaction_returns_none_for_regular_log(isolated_db):
    """Pass a regular log line, assert None returned."""
    from app.services.setup_execution_service import SetupExecutionService

    result = SetupExecutionService._try_parse_interaction("INFO: Server starting on port 8080")
    assert result is None

    result = SetupExecutionService._try_parse_interaction("Installing dependencies...")
    assert result is None

    result = SetupExecutionService._try_parse_interaction('{"key": "value"}')
    assert result is None
