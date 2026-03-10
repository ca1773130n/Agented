"""Tests for /admin/rules API routes."""


def _create_rule(client, **overrides):
    """Helper to create a rule via API."""
    data = {
        "name": "Test Rule",
        "rule_type": "validation",
        "condition": "file_exists",
        "action": "reject",
        **overrides,
    }
    return client.post("/admin/rules/", json=data)


class TestListRules:
    def test_list_rules_empty(self, client):
        """GET /admin/rules/ returns empty list when none exist."""
        resp = client.get("/admin/rules/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["rules"] == []
        assert body["total_count"] == 0

    def test_list_rules_populated(self, client):
        """GET /admin/rules/ returns created rules."""
        _create_rule(client, name="Rule A")
        _create_rule(client, name="Rule B")
        resp = client.get("/admin/rules/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["rules"]) == 2
        assert body["total_count"] == 2


class TestCreateRule:
    def test_create_rule(self, client):
        """POST /admin/rules/ creates a rule and returns 201."""
        resp = _create_rule(client, name="My Rule")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Rule created"
        assert body["rule"]["name"] == "My Rule"

    def test_create_rule_missing_name(self, client):
        """POST /admin/rules/ without name returns 422."""
        resp = client.post("/admin/rules/", json={"rule_type": "validation"})
        assert resp.status_code == 422

    def test_create_rule_invalid_type(self, client):
        """POST /admin/rules/ with invalid rule_type returns 422."""
        resp = client.post("/admin/rules/", json={"name": "Bad", "rule_type": "invalid_type"})
        assert resp.status_code == 422


class TestGetRule:
    def test_get_rule(self, client):
        """GET /admin/rules/:id returns rule details."""
        create_resp = _create_rule(client)
        rule_id = create_resp.get_json()["rule"]["id"]

        resp = client.get(f"/admin/rules/{rule_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == rule_id
        assert body["name"] == "Test Rule"

    def test_get_rule_not_found(self, client):
        """GET /admin/rules/:id returns 404 for nonexistent rule."""
        resp = client.get("/admin/rules/99999")
        assert resp.status_code == 404


class TestUpdateRule:
    def test_update_rule(self, client):
        """PUT /admin/rules/:id updates the rule."""
        create_resp = _create_rule(client)
        rule_id = create_resp.get_json()["rule"]["id"]

        resp = client.put(f"/admin/rules/{rule_id}", json={"name": "Updated Rule"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["name"] == "Updated Rule"

    def test_update_rule_not_found(self, client):
        """PUT /admin/rules/:id returns 404 for nonexistent rule."""
        resp = client.put("/admin/rules/99999", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteRule:
    def test_delete_rule(self, client):
        """DELETE /admin/rules/:id deletes the rule."""
        create_resp = _create_rule(client)
        rule_id = create_resp.get_json()["rule"]["id"]

        resp = client.delete(f"/admin/rules/{rule_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Rule deleted"

        # Verify it's gone
        resp = client.get(f"/admin/rules/{rule_id}")
        assert resp.status_code == 404

    def test_delete_rule_not_found(self, client):
        """DELETE /admin/rules/:id returns 404 for nonexistent rule."""
        resp = client.delete("/admin/rules/99999")
        assert resp.status_code == 404


class TestRuleTypes:
    def test_list_rule_types(self, client):
        """GET /admin/rules/types returns valid rule types."""
        resp = client.get("/admin/rules/types")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "pre_check" in body["types"]
        assert "validation" in body["types"]

    def test_export_rule(self, client):
        """GET /admin/rules/:id/export returns exportable rule config."""
        create_resp = _create_rule(client, name="Export Rule")
        rule_id = create_resp.get_json()["rule"]["id"]

        resp = client.get(f"/admin/rules/{rule_id}/export")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["rule"]["name"] == "Export Rule"
        assert body["format"] == "json"

    def test_export_rule_not_found(self, client):
        """GET /admin/rules/:id/export returns 404 for nonexistent rule."""
        resp = client.get("/admin/rules/99999/export")
        assert resp.status_code == 404
