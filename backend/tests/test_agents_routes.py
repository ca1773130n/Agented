"""Tests for /admin/agents API routes."""


def _create_agent(client, **overrides):
    """Helper to create an agent via API."""
    data = {"name": "Test Agent", "description": "A test agent", **overrides}
    return client.post("/admin/agents/", json=data)


class TestListAgents:
    def test_list_agents_empty(self, client):
        """GET /admin/agents/ returns empty list when none exist."""
        resp = client.get("/admin/agents/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["agents"] == []
        assert body["total_count"] == 0

    def test_list_agents_populated(self, client):
        """GET /admin/agents/ returns created agents."""
        _create_agent(client, name="Agent A")
        _create_agent(client, name="Agent B")
        resp = client.get("/admin/agents/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["agents"]) == 2
        assert body["total_count"] == 2


class TestCreateAgent:
    def test_create_agent(self, client):
        """POST /admin/agents/ creates an agent and returns 201."""
        resp = _create_agent(client, name="My Agent")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Agent created"
        assert body["agent_id"].startswith("agent-")
        assert body["name"] == "My Agent"

    def test_create_agent_missing_name(self, client):
        """POST /admin/agents/ without name returns 422 (Pydantic validation)."""
        resp = client.post("/admin/agents/", json={"description": "no name"})
        assert resp.status_code == 422


class TestGetAgent:
    def test_get_agent(self, client):
        """GET /admin/agents/:id returns agent details."""
        create_resp = _create_agent(client)
        agent_id = create_resp.get_json()["agent_id"]

        resp = client.get(f"/admin/agents/{agent_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == agent_id
        assert body["name"] == "Test Agent"

    def test_get_agent_not_found(self, client):
        """GET /admin/agents/:id returns 404 for nonexistent agent."""
        resp = client.get("/admin/agents/agent-nonexistent")
        assert resp.status_code == 404


class TestUpdateAgent:
    def test_update_agent(self, client):
        """PUT /admin/agents/:id updates the agent."""
        create_resp = _create_agent(client)
        agent_id = create_resp.get_json()["agent_id"]

        resp = client.put(f"/admin/agents/{agent_id}", json={"name": "Updated Agent"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Agent updated"

    def test_update_agent_not_found(self, client):
        """PUT /admin/agents/:id returns 404 for nonexistent agent."""
        resp = client.put("/admin/agents/agent-nonexistent", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteAgent:
    def test_delete_agent(self, client):
        """DELETE /admin/agents/:id deletes the agent."""
        create_resp = _create_agent(client)
        agent_id = create_resp.get_json()["agent_id"]

        resp = client.delete(f"/admin/agents/{agent_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Agent deleted"

        # Verify it's gone
        resp = client.get(f"/admin/agents/{agent_id}")
        assert resp.status_code == 404

    def test_delete_agent_not_found(self, client):
        """DELETE /admin/agents/:id returns 404 for nonexistent agent."""
        resp = client.delete("/admin/agents/agent-nonexistent")
        assert resp.status_code == 404
