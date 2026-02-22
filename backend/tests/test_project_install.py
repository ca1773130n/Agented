"""Tests for project component installation (install/uninstall via .claude/ files)."""

import json
import os

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_workspace(tmp_path, monkeypatch):
    """Mock workspace resolution to use a temp directory."""
    workspace = str(tmp_path / "workspace")
    os.makedirs(workspace, exist_ok=True)

    def mock_resolve(project_id):
        return workspace

    monkeypatch.setattr(
        "app.services.project_install_service.ProjectWorkspaceService.resolve_working_directory",
        mock_resolve,
    )
    return workspace


@pytest.fixture
def project_id(isolated_db):
    """Create a project and return its ID."""
    from app.database import add_project

    pid = add_project(name="Test Project", local_path="/tmp/test-project")
    return pid


def _create_agent(isolated_db):
    """Create a minimal agent and return its ID."""
    from app.database import _get_unique_agent_id, get_connection

    with get_connection() as conn:
        agent_id = _get_unique_agent_id(conn)
        conn.execute(
            "INSERT INTO agents (id, name, backend_type, description, role, context) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, "Test Agent", "claude", "A test agent", "developer", "Agent context body"),
        )
        conn.commit()
    return agent_id


def _create_hook(isolated_db):
    """Create a hook and return its ID."""
    from app.database import add_hook

    return add_hook(
        name="Pre-commit check",
        event="PreToolUse",
        description="Validates tool usage",
        content="Check that the tool call is valid.",
    )


def _create_command(isolated_db):
    """Create a command and return its ID."""
    from app.database import add_command

    return add_command(
        name="Deploy Staging",
        description="Deploy to staging environment",
        content="Run the deployment script for staging.",
    )


def _create_rule(isolated_db):
    """Create a rule and return its ID."""
    from app.database import add_rule

    return add_rule(
        name="No console.log",
        rule_type="validation",
        description="Prevent console.log in production code",
        condition="File contains console.log",
        action="Remove console.log statements",
    )


# ---------------------------------------------------------------------------
# Test 1: Install agent
# ---------------------------------------------------------------------------


def test_install_agent(client, isolated_db, project_id, mock_workspace):
    """Install an agent and verify .claude/agents/{name}.md exists with YAML frontmatter."""
    agent_id = _create_agent(isolated_db)

    resp = client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "agent", "component_id": agent_id},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["installed"] is True
    assert "agents/" in data["path"]

    # Verify file exists
    full_path = os.path.join(mock_workspace, data["path"])
    assert os.path.isfile(full_path), f"Expected file at {full_path}"

    # Verify YAML frontmatter
    content = open(full_path).read()
    assert content.startswith("---")
    assert "name: Test Agent" in content


# ---------------------------------------------------------------------------
# Test 2: Install hook with settings.json
# ---------------------------------------------------------------------------


def test_install_hook_with_settings_json(client, isolated_db, project_id, mock_workspace):
    """Install a hook and verify both .claude/hooks/{name}.md and settings.json."""
    hook_id = _create_hook(isolated_db)

    resp = client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "hook", "component_id": str(hook_id)},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["installed"] is True

    # Verify hook file exists
    full_path = os.path.join(mock_workspace, data["path"])
    assert os.path.isfile(full_path)

    content = open(full_path).read()
    assert "name: Pre-commit check" in content
    assert "event: PreToolUse" in content

    # Verify settings.json has hook entry
    settings_path = os.path.join(mock_workspace, ".claude", "settings.json")
    assert os.path.isfile(settings_path)

    settings = json.load(open(settings_path))
    assert "hooks" in settings
    assert "PreToolUse" in settings["hooks"]
    assert any(h["name"] == "Pre-commit check" for h in settings["hooks"]["PreToolUse"])


# ---------------------------------------------------------------------------
# Test 3: Install command
# ---------------------------------------------------------------------------


def test_install_command(client, isolated_db, project_id, mock_workspace):
    """Install a command and verify .claude/commands/{name}.md exists."""
    cmd_id = _create_command(isolated_db)

    resp = client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "command", "component_id": str(cmd_id)},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["installed"] is True
    assert "commands/" in data["path"]

    full_path = os.path.join(mock_workspace, data["path"])
    assert os.path.isfile(full_path)

    content = open(full_path).read()
    assert "name: Deploy Staging" in content


# ---------------------------------------------------------------------------
# Test 4: Install rule
# ---------------------------------------------------------------------------


def test_install_rule(client, isolated_db, project_id, mock_workspace):
    """Install a rule and verify .claude/rules/{name}.md exists."""
    rule_id = _create_rule(isolated_db)

    resp = client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "rule", "component_id": str(rule_id)},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["installed"] is True
    assert "rules/" in data["path"]

    full_path = os.path.join(mock_workspace, data["path"])
    assert os.path.isfile(full_path)

    content = open(full_path).read()
    assert "name: No console.log" in content
    assert "rule_type: validation" in content


# ---------------------------------------------------------------------------
# Test 5: Uninstall component
# ---------------------------------------------------------------------------


def test_uninstall_component(client, isolated_db, project_id, mock_workspace):
    """Install then uninstall and verify file removed and DB record deleted."""
    cmd_id = _create_command(isolated_db)

    # Install first
    resp = client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "command", "component_id": str(cmd_id)},
    )
    assert resp.status_code == 200
    install_data = resp.get_json()
    full_path = os.path.join(mock_workspace, install_data["path"])
    assert os.path.isfile(full_path)

    # Uninstall
    resp = client.post(
        f"/admin/projects/{project_id}/uninstall",
        json={"component_type": "command", "component_id": str(cmd_id)},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["uninstalled"] is True

    # Verify file removed
    assert not os.path.isfile(full_path)

    # Verify DB record gone
    from app.database import get_project_installation

    assert get_project_installation(project_id, "command", str(cmd_id)) is None


# ---------------------------------------------------------------------------
# Test 6: List installations
# ---------------------------------------------------------------------------


def test_list_installations(client, isolated_db, project_id, mock_workspace):
    """Install 2 components and verify list returns both with names."""
    agent_id = _create_agent(isolated_db)
    cmd_id = _create_command(isolated_db)

    client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "agent", "component_id": agent_id},
    )
    client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "command", "component_id": str(cmd_id)},
    )

    resp = client.get(f"/admin/projects/{project_id}/installations")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["installations"]) == 2

    names = [i["component_name"] for i in data["installations"]]
    assert "Test Agent" in names
    assert "Deploy Staging" in names


# ---------------------------------------------------------------------------
# Test 7: Install duplicate is idempotent
# ---------------------------------------------------------------------------


def test_install_duplicate_is_idempotent(client, isolated_db, project_id, mock_workspace):
    """Install same component twice and verify no error."""
    cmd_id = _create_command(isolated_db)

    resp1 = client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "command", "component_id": str(cmd_id)},
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "command", "component_id": str(cmd_id)},
    )
    assert resp2.status_code == 200

    # Should still only have one installation record
    resp = client.get(f"/admin/projects/{project_id}/installations")
    data = resp.get_json()
    command_installs = [i for i in data["installations"] if i["component_type"] == "command"]
    assert len(command_installs) == 1


# ---------------------------------------------------------------------------
# Test 8: Install invalid component type returns 400
# ---------------------------------------------------------------------------


def test_install_invalid_component_type(client, isolated_db, project_id):
    """Verify 400 error for invalid component_type."""
    resp = client.post(
        f"/admin/projects/{project_id}/install",
        json={"component_type": "invalid", "component_id": "123"},
    )
    assert resp.status_code == 400
    assert "component_type" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Test 9: Auto-clone on project create
# ---------------------------------------------------------------------------


def test_auto_clone_on_project_create(client, isolated_db, tmp_path, monkeypatch):
    """Create project with github_repo and verify clone_status in response."""

    # Mock GitHubService.validate_repo_url to return True
    monkeypatch.setattr(
        "app.routes.projects.GitHubService.validate_repo_url",
        lambda repo: True,
    )

    # Mock ProjectWorkspaceService.clone_async to be a no-op
    monkeypatch.setattr(
        "app.routes.projects.ProjectWorkspaceService.clone_async",
        lambda pid: None,
    )

    resp = client.post(
        "/admin/projects/",
        json={"name": "Auto Clone Project", "github_repo": "org/repo"},
    )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    assert data["clone_status"] == "cloning"
    assert "project" in data
