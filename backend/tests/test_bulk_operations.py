"""Tests for bulk operation endpoints (API-05)."""

import pytest


@pytest.fixture
def client(isolated_db):
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# =============================================================================
# Bulk agent tests
# =============================================================================


class TestBulkAgents:
    def test_bulk_create_10_agents(self, client):
        """Bulk create 10 agents in one request with per-item results."""
        items = [{"name": f"Agent {i}", "description": f"Desc {i}"} for i in range(10)]
        resp = client.post("/admin/bulk/agents", json={"action": "create", "items": items})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 10
        assert data["succeeded"] == 10
        assert data["failed"] == 0
        for r in data["results"]:
            assert r["success"] is True
            assert r["id"] is not None
            assert r["id"].startswith("agent-")

    def test_bulk_update_agents(self, client):
        """Bulk update 5 agents' names."""
        # Create agents first
        items = [{"name": f"Agent {i}"} for i in range(5)]
        resp = client.post("/admin/bulk/agents", json={"action": "create", "items": items})
        created = resp.get_json()["results"]

        # Update their names
        updates = [
            {"id": r["id"], "name": f"Updated Agent {i}"}
            for i, r in enumerate(created)
        ]
        resp = client.post("/admin/bulk/agents", json={"action": "update", "items": updates})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["succeeded"] == 5
        assert data["failed"] == 0

    def test_bulk_delete_agents(self, client):
        """Bulk delete 5 agents."""
        # Create agents first
        items = [{"name": f"Agent {i}"} for i in range(5)]
        resp = client.post("/admin/bulk/agents", json={"action": "create", "items": items})
        created = resp.get_json()["results"]

        # Delete them
        deletes = [{"id": r["id"]} for r in created]
        resp = client.post("/admin/bulk/agents", json={"action": "delete", "items": deletes})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["succeeded"] == 5
        assert data["failed"] == 0

    def test_per_item_failure_isolation(self, client):
        """One item failing does not affect others."""
        items = [
            {"name": "Good Agent 1"},
            {"description": "Missing name"},  # No name - should fail
            {"name": "Good Agent 2"},
        ]
        resp = client.post("/admin/bulk/agents", json={"action": "create", "items": items})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 3
        assert data["succeeded"] == 2
        assert data["failed"] == 1
        # Item 0 and 2 succeed, item 1 fails
        assert data["results"][0]["success"] is True
        assert data["results"][1]["success"] is False
        assert "name" in data["results"][1]["error"].lower()
        assert data["results"][2]["success"] is True

    def test_max_items_limit(self, client):
        """Send 101 items, should be rejected."""
        items = [{"name": f"Agent {i}"} for i in range(101)]
        resp = client.post("/admin/bulk/agents", json={"action": "create", "items": items})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "100" in data["error"]

    def test_invalid_action(self, client):
        """Invalid action should return 400."""
        resp = client.post(
            "/admin/bulk/agents", json={"action": "invalid", "items": [{"name": "x"}]}
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "invalid" in data["error"].lower() or "action" in data["error"].lower()

    def test_empty_items(self, client):
        """Empty items array returns 0 results."""
        resp = client.post("/admin/bulk/agents", json={"action": "create", "items": []})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0
        assert data["succeeded"] == 0
        assert data["failed"] == 0

    def test_missing_body(self, client):
        """Missing JSON body returns 400."""
        resp = client.post("/admin/bulk/agents", content_type="application/json")
        assert resp.status_code == 400

    def test_missing_action(self, client):
        """Missing action field returns 400."""
        resp = client.post("/admin/bulk/agents", json={"items": [{"name": "x"}]})
        assert resp.status_code == 400

    def test_items_not_list(self, client):
        """Items not a list returns 400."""
        resp = client.post(
            "/admin/bulk/agents", json={"action": "create", "items": "not a list"}
        )
        assert resp.status_code == 400


# =============================================================================
# Bulk trigger tests
# =============================================================================


class TestBulkTriggers:
    def test_bulk_create_triggers(self, client):
        """Bulk create triggers."""
        items = [
            {"name": f"Trigger {i}", "prompt_template": f"Template {i}"}
            for i in range(3)
        ]
        resp = client.post("/admin/bulk/triggers", json={"action": "create", "items": items})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["succeeded"] == 3
        for r in data["results"]:
            assert r["success"] is True

    def test_bulk_delete_predefined_trigger_rejected(self, client):
        """Predefined triggers cannot be bulk-deleted."""
        items = [{"id": "bot-security"}]
        resp = client.post("/admin/bulk/triggers", json={"action": "delete", "items": items})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["failed"] == 1
        assert "predefined" in data["results"][0]["error"].lower()


# =============================================================================
# Bulk plugin tests
# =============================================================================


class TestBulkPlugins:
    def test_bulk_create_plugins(self, client):
        """Bulk create plugins."""
        items = [{"name": f"Plugin {i}"} for i in range(3)]
        resp = client.post("/admin/bulk/plugins", json={"action": "create", "items": items})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["succeeded"] == 3

    def test_bulk_delete_plugins(self, client):
        """Bulk create then delete plugins."""
        items = [{"name": f"Plugin {i}"} for i in range(2)]
        resp = client.post("/admin/bulk/plugins", json={"action": "create", "items": items})
        created = resp.get_json()["results"]

        deletes = [{"id": r["id"]} for r in created]
        resp = client.post("/admin/bulk/plugins", json={"action": "delete", "items": deletes})
        assert resp.status_code == 200
        assert resp.get_json()["succeeded"] == 2


# =============================================================================
# Bulk hook tests
# =============================================================================


class TestBulkHooks:
    def test_bulk_create_hooks(self, client):
        """Bulk create hooks."""
        items = [{"name": f"Hook {i}", "event": "on_push"} for i in range(3)]
        resp = client.post("/admin/bulk/hooks", json={"action": "create", "items": items})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["succeeded"] == 3

    def test_bulk_update_hooks(self, client):
        """Bulk create then update hooks."""
        items = [{"name": f"Hook {i}", "event": "on_push"} for i in range(2)]
        resp = client.post("/admin/bulk/hooks", json={"action": "create", "items": items})
        created = resp.get_json()["results"]

        updates = [{"id": r["id"], "name": f"Updated Hook {i}"} for i, r in enumerate(created)]
        resp = client.post("/admin/bulk/hooks", json={"action": "update", "items": updates})
        assert resp.status_code == 200
        assert resp.get_json()["succeeded"] == 2
