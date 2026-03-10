"""Tests for /admin/commands API routes."""


def _create_command(client, **overrides):
    """Helper to create a command via API."""
    data = {"name": "Test Command", "content": "echo hello", **overrides}
    return client.post("/admin/commands/", json=data)


class TestListCommands:
    def test_list_commands_empty(self, client):
        """GET /admin/commands/ returns empty list when none exist."""
        resp = client.get("/admin/commands/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["commands"] == []
        assert body["total_count"] == 0

    def test_list_commands_populated(self, client):
        """GET /admin/commands/ returns created commands."""
        _create_command(client, name="Cmd A")
        _create_command(client, name="Cmd B")
        resp = client.get("/admin/commands/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["commands"]) == 2
        assert body["total_count"] == 2


class TestCreateCommand:
    def test_create_command(self, client):
        """POST /admin/commands/ creates a command and returns 201."""
        resp = _create_command(client, name="My Command")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Command created"
        assert body["command"]["name"] == "My Command"

    def test_create_command_missing_name(self, client):
        """POST /admin/commands/ without name returns 422."""
        resp = client.post("/admin/commands/", json={"content": "echo hi"})
        assert resp.status_code == 422


class TestGetCommand:
    def test_get_command(self, client):
        """GET /admin/commands/:id returns command details."""
        create_resp = _create_command(client)
        cmd_id = create_resp.get_json()["command"]["id"]

        resp = client.get(f"/admin/commands/{cmd_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == cmd_id
        assert body["name"] == "Test Command"

    def test_get_command_not_found(self, client):
        """GET /admin/commands/:id returns 404 for nonexistent command."""
        resp = client.get("/admin/commands/99999")
        assert resp.status_code == 404


class TestUpdateCommand:
    def test_update_command(self, client):
        """PUT /admin/commands/:id updates the command."""
        create_resp = _create_command(client)
        cmd_id = create_resp.get_json()["command"]["id"]

        resp = client.put(f"/admin/commands/{cmd_id}", json={"name": "Updated Command"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["name"] == "Updated Command"

    def test_update_command_not_found(self, client):
        """PUT /admin/commands/:id returns 404 for nonexistent command."""
        resp = client.put("/admin/commands/99999", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteCommand:
    def test_delete_command(self, client):
        """DELETE /admin/commands/:id deletes the command."""
        create_resp = _create_command(client)
        cmd_id = create_resp.get_json()["command"]["id"]

        resp = client.delete(f"/admin/commands/{cmd_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Command deleted"

        # Verify it's gone
        resp = client.get(f"/admin/commands/{cmd_id}")
        assert resp.status_code == 404

    def test_delete_command_not_found(self, client):
        """DELETE /admin/commands/:id returns 404 for nonexistent command."""
        resp = client.delete("/admin/commands/99999")
        assert resp.status_code == 404


class TestProjectCommands:
    def test_list_project_commands(self, client):
        """GET /admin/commands/project/:id returns commands for a project."""
        _create_command(client, name="Proj Cmd", project_id="proj-abc123")
        resp = client.get("/admin/commands/project/proj-abc123")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["project_id"] == "proj-abc123"
        assert isinstance(body["commands"], list)

    def test_list_project_commands_empty(self, client):
        """GET /admin/commands/project/:id returns empty list for project with no commands."""
        resp = client.get("/admin/commands/project/proj-empty")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["commands"] == []
