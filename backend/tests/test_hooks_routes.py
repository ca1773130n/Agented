"""Tests for /admin/hooks API routes."""


def _create_hook(client, **overrides):
    """Helper to create a hook via API."""
    data = {"name": "Test Hook", "event": "PreToolUse", "content": "echo check", **overrides}
    return client.post("/admin/hooks/", json=data)


class TestListHooks:
    def test_list_hooks_empty(self, client):
        """GET /admin/hooks/ returns empty list when none exist."""
        resp = client.get("/admin/hooks/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["hooks"] == []
        assert body["total_count"] == 0

    def test_list_hooks_populated(self, client):
        """GET /admin/hooks/ returns created hooks."""
        _create_hook(client, name="Hook A")
        _create_hook(client, name="Hook B")
        resp = client.get("/admin/hooks/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["hooks"]) == 2
        assert body["total_count"] == 2


class TestCreateHook:
    def test_create_hook(self, client):
        """POST /admin/hooks/ creates a hook and returns 201."""
        resp = _create_hook(client, name="My Hook")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Hook created"
        assert body["hook"]["name"] == "My Hook"

    def test_create_hook_missing_name(self, client):
        """POST /admin/hooks/ without name returns 422."""
        resp = client.post("/admin/hooks/", json={"event": "PreToolUse"})
        assert resp.status_code == 422

    def test_create_hook_invalid_event(self, client):
        """POST /admin/hooks/ with invalid event returns 422."""
        resp = client.post("/admin/hooks/", json={"name": "Bad", "event": "InvalidEvent"})
        assert resp.status_code == 422


class TestGetHook:
    def test_get_hook(self, client):
        """GET /admin/hooks/:id returns hook details."""
        create_resp = _create_hook(client)
        hook_id = create_resp.get_json()["hook"]["id"]

        resp = client.get(f"/admin/hooks/{hook_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == hook_id
        assert body["name"] == "Test Hook"

    def test_get_hook_not_found(self, client):
        """GET /admin/hooks/:id returns 404 for nonexistent hook."""
        resp = client.get("/admin/hooks/99999")
        assert resp.status_code == 404


class TestUpdateHook:
    def test_update_hook(self, client):
        """PUT /admin/hooks/:id updates the hook."""
        create_resp = _create_hook(client)
        hook_id = create_resp.get_json()["hook"]["id"]

        resp = client.put(f"/admin/hooks/{hook_id}", json={"name": "Updated Hook"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["name"] == "Updated Hook"

    def test_update_hook_not_found(self, client):
        """PUT /admin/hooks/:id returns 404 for nonexistent hook."""
        resp = client.put("/admin/hooks/99999", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteHook:
    def test_delete_hook(self, client):
        """DELETE /admin/hooks/:id deletes the hook."""
        create_resp = _create_hook(client)
        hook_id = create_resp.get_json()["hook"]["id"]

        resp = client.delete(f"/admin/hooks/{hook_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Hook deleted"

        # Verify it's gone
        resp = client.get(f"/admin/hooks/{hook_id}")
        assert resp.status_code == 404

    def test_delete_hook_not_found(self, client):
        """DELETE /admin/hooks/:id returns 404 for nonexistent hook."""
        resp = client.delete("/admin/hooks/99999")
        assert resp.status_code == 404


class TestHookEvents:
    def test_list_hook_events(self, client):
        """GET /admin/hooks/events returns valid event types."""
        resp = client.get("/admin/hooks/events")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "PreToolUse" in body["events"]
        assert "PostToolUse" in body["events"]
