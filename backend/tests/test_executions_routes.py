"""Tests for /admin/executions API routes."""


class TestListAllExecutions:
    def test_list_all_executions_empty(self, client):
        """GET /admin/executions returns empty list when no executions exist."""
        resp = client.get("/admin/executions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "executions" in body
        assert body["total"] == 0
        assert body["total_count"] == 0

    def test_list_all_executions_with_filters(self, client):
        """GET /admin/executions with filter params returns 200."""
        resp = client.get("/admin/executions?status=completed&limit=10&offset=0")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "executions" in body


class TestListTriggerExecutions:
    def test_list_trigger_executions(self, client):
        """GET /admin/triggers/:id/executions returns 200 for predefined trigger."""
        # bot-security is seeded by the isolated_db fixture
        resp = client.get("/admin/triggers/bot-security/executions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "executions" in body
        assert "total_count" in body

    def test_list_trigger_executions_not_found(self, client):
        """GET /admin/triggers/:id/executions returns 404 for nonexistent trigger."""
        resp = client.get("/admin/triggers/bot-nonexistent/executions")
        assert resp.status_code == 404


class TestGetExecution:
    def test_get_execution_not_found(self, client):
        """GET /admin/executions/:id returns 404 for nonexistent execution."""
        resp = client.get("/admin/executions/exec-nonexistent")
        assert resp.status_code == 404


class TestCancelExecution:
    def test_cancel_execution_not_found(self, client):
        """DELETE /admin/executions/:id returns 404 for nonexistent execution."""
        resp = client.delete("/admin/executions/exec-nonexistent")
        assert resp.status_code == 404

    def test_cancel_post_not_found(self, client):
        """POST /admin/executions/:id/cancel returns 404 for nonexistent execution."""
        resp = client.post("/admin/executions/exec-nonexistent/cancel")
        assert resp.status_code == 404


class TestRunningTriggerExecution:
    def test_get_running_for_trigger(self, client):
        """GET /admin/triggers/:id/executions/running returns status for predefined trigger."""
        resp = client.get("/admin/triggers/bot-security/executions/running")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "running" in body

    def test_get_running_trigger_not_found(self, client):
        """GET /admin/triggers/:id/executions/running returns 404 for nonexistent trigger."""
        resp = client.get("/admin/triggers/bot-nonexistent/executions/running")
        assert resp.status_code == 404


class TestExecutionQueue:
    def test_get_queue_status(self, client):
        """GET /admin/executions/queue returns queue summary."""
        resp = client.get("/admin/executions/queue")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "queue" in body
        assert "total_pending" in body

    def test_get_queue_for_trigger(self, client):
        """GET /admin/executions/queue/:trigger_id returns pending count."""
        resp = client.get("/admin/executions/queue/bot-security")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["trigger_id"] == "bot-security"
        assert "pending" in body


class TestPendingRetries:
    def test_get_pending_retries(self, client):
        """GET /admin/executions/retries returns retries list."""
        resp = client.get("/admin/executions/retries")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "retries" in body
        assert "total" in body
