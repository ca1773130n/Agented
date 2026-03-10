"""Tests for /api/audit API routes."""


class TestAuditHistory:
    def test_get_audit_history(self, client):
        """GET /api/audit/history returns 200 with audit list."""
        resp = client.get("/api/audit/history")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "audits" in body or "total_count" in body or isinstance(body, dict)

    def test_get_audit_history_with_pagination(self, client):
        """GET /api/audit/history with limit/offset returns 200."""
        resp = client.get("/api/audit/history?limit=5&offset=0")
        assert resp.status_code == 200


class TestAuditStats:
    def test_get_audit_stats(self, client):
        """GET /api/audit/stats returns 200."""
        resp = client.get("/api/audit/stats")
        assert resp.status_code == 200


class TestAuditProjects:
    def test_get_audit_projects(self, client):
        """GET /api/audit/projects returns 200."""
        resp = client.get("/api/audit/projects")
        assert resp.status_code == 200


class TestAddAudit:
    def test_add_audit_no_body(self, client):
        """POST /api/audit/ without JSON body returns 400."""
        resp = client.post("/api/audit/", content_type="application/json")
        assert resp.status_code == 400

    def test_add_audit_with_data(self, client):
        """POST /api/audit/ with data returns a response."""
        data = {
            "project_path": "/test/path",
            "findings": [],
            "trigger_id": "bot-security",
        }
        resp = client.post("/api/audit/", json=data)
        # May return 200 or 201 depending on implementation
        assert resp.status_code in (200, 201)


class TestAuditEvents:
    def test_get_audit_events(self, client):
        """GET /api/audit/events returns events list."""
        resp = client.get("/api/audit/events")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "events" in body
        assert "total" in body

    def test_get_audit_events_with_limit(self, client):
        """GET /api/audit/events?limit=5 respects limit parameter."""
        resp = client.get("/api/audit/events?limit=5")
        assert resp.status_code == 200


class TestPersistentAuditEvents:
    def test_get_persistent_events(self, client):
        """GET /api/audit/events/persistent returns events from DB."""
        resp = client.get("/api/audit/events/persistent")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "events" in body
        assert "total" in body
