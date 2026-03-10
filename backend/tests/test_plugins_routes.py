"""Tests for /admin/plugins API routes."""


def _create_plugin(client, **overrides):
    """Helper to create a plugin via API."""
    data = {"name": "Test Plugin", "description": "A test plugin", **overrides}
    return client.post("/admin/plugins/", json=data)


class TestListPlugins:
    def test_list_plugins_empty(self, client):
        """GET /admin/plugins/ returns empty list when none exist."""
        resp = client.get("/admin/plugins/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["plugins"] == []
        assert body["total_count"] == 0

    def test_list_plugins_populated(self, client):
        """GET /admin/plugins/ returns created plugins."""
        _create_plugin(client, name="Plugin A")
        _create_plugin(client, name="Plugin B")
        resp = client.get("/admin/plugins/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["plugins"]) == 2
        assert body["total_count"] == 2


class TestCreatePlugin:
    def test_create_plugin(self, client):
        """POST /admin/plugins/ creates a plugin and returns 201."""
        resp = _create_plugin(client, name="My Plugin")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Plugin created"
        assert body["plugin"]["name"] == "My Plugin"
        assert body["plugin"]["id"].startswith("plug-")

    def test_create_plugin_missing_name(self, client):
        """POST /admin/plugins/ without name returns 422."""
        resp = client.post("/admin/plugins/", json={"description": "no name"})
        assert resp.status_code == 422


class TestGetPlugin:
    def test_get_plugin(self, client):
        """GET /admin/plugins/:id returns plugin details."""
        create_resp = _create_plugin(client)
        plugin_id = create_resp.get_json()["plugin"]["id"]

        resp = client.get(f"/admin/plugins/{plugin_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == plugin_id
        assert body["name"] == "Test Plugin"

    def test_get_plugin_not_found(self, client):
        """GET /admin/plugins/:id returns 404 for nonexistent plugin."""
        resp = client.get("/admin/plugins/plug-nonexistent")
        assert resp.status_code == 404


class TestUpdatePlugin:
    def test_update_plugin(self, client):
        """PUT /admin/plugins/:id updates the plugin."""
        create_resp = _create_plugin(client)
        plugin_id = create_resp.get_json()["plugin"]["id"]

        resp = client.put(f"/admin/plugins/{plugin_id}", json={"name": "Updated Plugin"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["name"] == "Updated Plugin"

    def test_update_plugin_not_found(self, client):
        """PUT /admin/plugins/:id returns 404 for nonexistent plugin."""
        resp = client.put("/admin/plugins/plug-nonexistent", json={"name": "X"})
        assert resp.status_code == 404


class TestDeletePlugin:
    def test_delete_plugin(self, client):
        """DELETE /admin/plugins/:id deletes the plugin."""
        create_resp = _create_plugin(client)
        plugin_id = create_resp.get_json()["plugin"]["id"]

        resp = client.delete(f"/admin/plugins/{plugin_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Plugin deleted"

        # Verify it's gone
        resp = client.get(f"/admin/plugins/{plugin_id}")
        assert resp.status_code == 404

    def test_delete_plugin_not_found(self, client):
        """DELETE /admin/plugins/:id returns 404 for nonexistent plugin."""
        resp = client.delete("/admin/plugins/plug-nonexistent")
        assert resp.status_code == 404
