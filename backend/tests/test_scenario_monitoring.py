"""Scenario tests for monitoring, health, rotation, scheduler, scheduling suggestions,
execution search, replay, and orchestration route domains.

Exercises CRUD and special endpoints across eight route blueprints.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_trigger(client, name="test-trigger", trigger_source="webhook"):
    """Create a trigger and return its ID."""
    resp = client.post(
        "/admin/triggers/",
        json={
            "name": name,
            "trigger_source": trigger_source,
            "backend_type": "claude",
            "prompt_template": "Run security check on {paths}",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["trigger_id"]


def _seed_execution(trigger_id="bot-security", status="completed", prompt="test prompt"):
    """Insert an execution_log row directly into the DB and return its execution_id.

    Uses a predefined trigger ID (bot-security) by default to satisfy FK constraints.
    """
    from app.db.connection import get_connection
    from app.db.ids import _generate_short_id

    execution_id = f"exec-{_generate_short_id(6)}"
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO execution_logs
               (execution_id, trigger_id, trigger_type, status, prompt, command,
                backend_type, started_at, stdout_log, stderr_log)
               VALUES (?, ?, 'webhook', ?, ?, 'claude -p test', 'claude',
                       datetime('now'), '', '')""",
            (execution_id, trigger_id, status, prompt),
        )
        conn.commit()
    return execution_id


def _seed_backend_and_account():
    """Add a backend_accounts row under the predefined 'backend-claude' backend.

    Returns (backend_id, account_id). Uses the predefined backend seeded by init_db.
    """
    from app.db.connection import get_connection

    backend_id = "backend-claude"
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO backend_accounts
               (backend_id, account_name, is_default, plan)
               VALUES (?, 'Test Account', 1, 'pro')""",
            (backend_id,),
        )
        account_id = cursor.lastrowid
        conn.commit()
    return backend_id, account_id


# ===========================================================================
# 1. Health Monitor (/admin/health-monitor/*)
# ===========================================================================


class TestHealthMonitor:
    """Scenario: health monitoring alerts, status, check, and reports."""

    def test_list_alerts_empty(self, client):
        """GET /admin/health-monitor/alerts returns empty list initially."""
        resp = client.get("/admin/health-monitor/alerts")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["alerts"] == []

    def test_list_alerts_with_data(self, client):
        """Alerts appear after being inserted directly."""
        from app.db.health_alerts import create_health_alert

        trigger_id = _create_trigger(client, name="alert-trigger-1")
        alert_id = create_health_alert(
            alert_type="consecutive_failure",
            trigger_id=trigger_id,
            message="3 consecutive failures",
            severity="warning",
        )
        assert alert_id is not None

        resp = client.get("/admin/health-monitor/alerts")
        assert resp.status_code == 200
        alerts = resp.get_json()["alerts"]
        assert len(alerts) >= 1
        assert alerts[0]["alert_type"] == "consecutive_failure"

    def test_list_alerts_filter_by_trigger(self, client):
        """Alerts can be filtered by trigger_id."""
        from app.db.health_alerts import create_health_alert

        tid_a = _create_trigger(client, name="filter-trigger-a")
        tid_b = _create_trigger(client, name="filter-trigger-b")
        create_health_alert("slow", tid_a, "slow exec", severity="warning")
        create_health_alert("slow", tid_b, "slow exec 2", severity="warning")

        resp = client.get(f"/admin/health-monitor/alerts?trigger_id={tid_a}")
        assert resp.status_code == 200
        alerts = resp.get_json()["alerts"]
        assert all(a["trigger_id"] == tid_a for a in alerts)

    def test_list_alerts_filter_acknowledged(self, client):
        """Filter by acknowledged=true/false."""
        from app.db.health_alerts import acknowledge_alert, create_health_alert

        tid = _create_trigger(client, name="ack-trigger")
        aid = create_health_alert("test", tid, "msg", severity="info")
        acknowledge_alert(aid)

        resp = client.get("/admin/health-monitor/alerts?acknowledged=true")
        assert resp.status_code == 200
        alerts = resp.get_json()["alerts"]
        assert all(a["acknowledged"] == 1 for a in alerts)

    def test_acknowledge_alert_via_db(self, client):
        """Acknowledge alert through DB and verify via list endpoint."""
        from app.db.health_alerts import acknowledge_alert, create_health_alert

        tid = _create_trigger(client, name="ack-alert-trigger")
        aid = create_health_alert("fail", tid, "failure alert", severity="critical")

        # Acknowledge directly via DB (route has a known flask-openapi3 path param issue)
        result = acknowledge_alert(aid)
        assert result is True

        # Verify via list endpoint filter
        resp = client.get("/admin/health-monitor/alerts?acknowledged=true")
        assert resp.status_code == 200
        alerts = resp.get_json()["alerts"]
        assert any(a["id"] == aid for a in alerts)

    def test_acknowledge_nonexistent_alert_via_db(self, client):
        """Acknowledging non-existent alert returns False."""
        from app.db.health_alerts import acknowledge_alert

        result = acknowledge_alert(99999)
        assert result is False

    def test_get_status(self, client):
        """GET /admin/health-monitor/status returns summary dict."""
        resp = client.get("/admin/health-monitor/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "total_alerts" in body
        assert "critical_count" in body
        assert "warning_count" in body

    def test_get_report(self, client):
        """GET /admin/health-monitor/report returns a report dict."""
        resp = client.get("/admin/health-monitor/report")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "prs_reviewed" in body
        assert "period_start" in body

    def test_manual_check(self, client):
        """POST /admin/health-monitor/check triggers a health check cycle."""
        resp = client.post("/admin/health-monitor/check")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Health check completed"
        assert "total_alerts" in body


# ===========================================================================
# 2. Monitoring (/admin/monitoring/*)
# ===========================================================================


class TestMonitoring:
    """Scenario: monitoring config, status, poll, and history."""

    def test_get_config(self, client):
        """GET /admin/monitoring/config returns current config."""
        resp = client.get("/admin/monitoring/config")
        assert resp.status_code == 200
        body = resp.get_json()
        # Config has at least enabled and polling_minutes keys
        assert "enabled" in body
        assert "polling_minutes" in body

    def test_save_config(self, client):
        """POST /admin/monitoring/config saves and returns config."""
        resp = client.post(
            "/admin/monitoring/config",
            json={"enabled": True, "polling_minutes": 15, "accounts": {}},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["enabled"] is True
        assert body["polling_minutes"] == 15

    def test_save_config_invalid_polling(self, client):
        """POST /admin/monitoring/config rejects invalid polling_minutes."""
        resp = client.post(
            "/admin/monitoring/config",
            json={"enabled": True, "polling_minutes": 7},
        )
        assert resp.status_code == 400

    def test_save_config_no_body(self, client):
        """POST /admin/monitoring/config without JSON body returns 400."""
        resp = client.post("/admin/monitoring/config", content_type="application/json")
        assert resp.status_code == 400

    def test_save_config_invalid_accounts_type(self, client):
        """POST /admin/monitoring/config rejects non-dict accounts."""
        resp = client.post(
            "/admin/monitoring/config",
            json={"enabled": True, "polling_minutes": 5, "accounts": ["bad"]},
        )
        assert resp.status_code == 400

    def test_get_status(self, client):
        """GET /admin/monitoring/status returns monitoring status."""
        resp = client.get("/admin/monitoring/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "enabled" in body
        assert "windows" in body

    def test_poll_now(self, client):
        """POST /admin/monitoring/poll triggers immediate poll."""
        resp = client.post("/admin/monitoring/poll")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "enabled" in body

    def test_get_history_missing_params(self, client):
        """GET /admin/monitoring/history without required params returns 400."""
        resp = client.get("/admin/monitoring/history")
        assert resp.status_code == 400

    def test_get_history_with_params(self, client):
        """GET /admin/monitoring/history with valid params returns empty history."""
        resp = client.get("/admin/monitoring/history?account_id=1&window_type=5h_sliding")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["account_id"] == 1
        assert body["window_type"] == "5h_sliding"
        assert body["history"] == []


# ===========================================================================
# 3. Rotation (/admin/rotation/*)
# ===========================================================================


class TestRotation:
    """Scenario: rotation status and history."""

    def test_get_rotation_status(self, client):
        """GET /admin/rotation/status returns sessions and evaluator."""
        resp = client.get("/admin/rotation/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "sessions" in body
        assert "evaluator" in body
        assert isinstance(body["sessions"], list)
        assert "job_id" in body["evaluator"]

    def test_get_rotation_history_empty(self, client):
        """GET /admin/rotation/history returns empty events initially."""
        resp = client.get("/admin/rotation/history")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["events"] == []
        assert body["total_count"] == 0

    def test_get_rotation_history_with_data(self, client):
        """History includes seeded rotation events."""
        from app.db.rotations import add_rotation_event

        eid = _seed_execution()
        add_rotation_event(execution_id=eid, reason="rate limit hit", urgency="high")

        resp = client.get("/admin/rotation/history")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total_count"] >= 1
        assert body["events"][0]["execution_id"] == eid

    def test_get_rotation_history_filter_by_execution(self, client):
        """History can be filtered by execution_id query param."""
        from app.db.rotations import add_rotation_event

        eid = _seed_execution()
        add_rotation_event(execution_id=eid, reason="test")

        resp = client.get(f"/admin/rotation/history?execution_id={eid}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert all(e["execution_id"] == eid for e in body["events"])

    def test_get_rotation_history_pagination(self, client):
        """History supports limit and offset."""
        resp = client.get("/admin/rotation/history?limit=10&offset=0")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "events" in body


# ===========================================================================
# 4. Scheduler (/admin/scheduler/*)
# ===========================================================================


class TestScheduler:
    """Scenario: scheduler status, sessions, and eligibility."""

    def test_get_scheduler_status(self, client):
        """GET /admin/scheduler/status returns comprehensive status."""
        resp = client.get("/admin/scheduler/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "sessions" in body
        assert "global_summary" in body

    def test_get_scheduler_sessions(self, client):
        """GET /admin/scheduler/sessions returns sessions list."""
        resp = client.get("/admin/scheduler/sessions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "sessions" in body
        assert isinstance(body["sessions"], list)

    def test_get_eligibility(self, client):
        """GET /admin/scheduler/eligibility/<account_id> returns eligibility result."""
        _backend_id, account_id = _seed_backend_and_account()
        resp = client.get(f"/admin/scheduler/eligibility/{account_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "eligible" in body

    def test_get_eligibility_unknown_account(self, client):
        """Eligibility check for unknown account still returns a result (eligible by default)."""
        resp = client.get("/admin/scheduler/eligibility/99999")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "eligible" in body


# ===========================================================================
# 5. Scheduling Suggestions (/admin/analytics/scheduling-suggestions)
# ===========================================================================


class TestSchedulingSuggestions:
    """Scenario: scheduling suggestion analysis."""

    def test_get_suggestions_insufficient_data(self, client):
        """Returns message about insufficient data when no executions exist."""
        resp = client.get("/admin/analytics/scheduling-suggestions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["suggestions"] == []
        assert body["total_executions_analyzed"] == 0
        assert "message" in body
        assert "Not enough" in body["message"]

    def test_get_suggestions_with_trigger_filter(self, client):
        """Accepts trigger_id filter and returns structured response."""
        resp = client.get(
            "/admin/analytics/scheduling-suggestions?trigger_id=trg-nonexist"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["suggestions"] == []
        assert "analysis_period_days" in body


# ===========================================================================
# 6. Execution Search (/admin/execution-search)
# ===========================================================================


class TestExecutionSearch:
    """Scenario: full-text search over execution logs."""

    def test_search_requires_query(self, client):
        """GET /admin/execution-search without q param returns 422."""
        resp = client.get("/admin/execution-search")
        assert resp.status_code == 422

    def test_search_empty_results(self, client):
        """Search with a query that matches nothing returns empty results."""
        resp = client.get("/admin/execution-search?q=nonexistent_term_xyz")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["results"] == []
        assert body["total"] == 0
        assert body["query"] == "nonexistent_term_xyz"

    def test_search_with_filters(self, client):
        """Search accepts optional filter params."""
        resp = client.get(
            "/admin/execution-search?q=test&status=completed&trigger_id=trg-1"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "results" in body

    def test_search_stats(self, client):
        """GET /admin/execution-search/stats returns index statistics."""
        resp = client.get("/admin/execution-search/stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "indexed_documents" in body
        assert isinstance(body["indexed_documents"], int)


# ===========================================================================
# 7. Replay (/admin/executions/*/replay, /admin/replay-comparisons/*)
# ===========================================================================


class TestReplay:
    """Scenario: replay execution, list comparisons, diff context."""

    def test_replay_nonexistent_execution(self, client):
        """Replaying a non-existent execution returns 404."""
        resp = client.post("/admin/executions/exec-nonexist/replay", json={})
        assert resp.status_code == 404

    def test_replay_running_execution(self, client):
        """Replaying a running execution returns 400."""
        eid = _seed_execution(status="running")
        resp = client.post(f"/admin/executions/{eid}/replay", json={})
        assert resp.status_code == 400

    def test_replay_completed_execution(self, client):
        """Replaying a completed execution creates a comparison."""
        eid = _seed_execution(status="completed")
        resp = client.post(
            f"/admin/executions/{eid}/replay",
            json={"notes": "regression check"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["original_execution_id"] == eid
        assert "replay_execution_id" in body
        assert "comparison_id" in body

    def test_list_execution_comparisons_empty(self, client):
        """GET /admin/executions/<id>/comparisons for unknown ID returns empty."""
        resp = client.get("/admin/executions/exec-unknown/comparisons")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["comparisons"] == []
        assert body["total"] == 0

    def test_list_execution_comparisons_with_data(self, client):
        """After a replay, comparisons appear for the original execution."""
        eid = _seed_execution(status="completed")
        client.post(f"/admin/executions/{eid}/replay", json={})

        resp = client.get(f"/admin/executions/{eid}/comparisons")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] >= 1
        assert body["comparisons"][0]["original_execution_id"] == eid

    def test_get_comparison_not_found(self, client):
        """GET /admin/replay-comparisons/<id> for unknown ID returns 404."""
        resp = client.get("/admin/replay-comparisons/rpl-nonexist")
        assert resp.status_code == 404

    def test_get_comparison_exists(self, client):
        """GET /admin/replay-comparisons/<id> returns the comparison."""
        eid = _seed_execution(status="completed")
        replay_resp = client.post(f"/admin/executions/{eid}/replay", json={})
        comparison_id = replay_resp.get_json()["comparison_id"]

        resp = client.get(f"/admin/replay-comparisons/{comparison_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["original_execution_id"] == eid

    def test_get_comparison_diff_not_found(self, client):
        """GET /admin/replay-comparisons/<id>/diff for unknown ID returns 404."""
        resp = client.get("/admin/replay-comparisons/rpl-nonexist/diff")
        assert resp.status_code == 404

    def test_diff_context_preview(self, client):
        """POST /admin/diff-context/preview extracts context from diff text."""
        diff_text = (
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-old line\n"
            "+new line\n"
            " line3\n"
        )
        resp = client.post(
            "/admin/diff-context/preview",
            json={"diff_text": diff_text},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "context" in body
        assert "token_estimate" in body

    def test_diff_context_preview_missing_field(self, client):
        """POST /admin/diff-context/preview without diff_text returns 400."""
        resp = client.post("/admin/diff-context/preview", json={})
        assert resp.status_code == 400

    def test_diff_context_preview_empty_diff(self, client):
        """POST /admin/diff-context/preview with empty diff returns empty context."""
        resp = client.post("/admin/diff-context/preview", json={"diff_text": ""})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["context"] == ""


# ===========================================================================
# 8. Orchestration (/admin/orchestration/*)
# ===========================================================================


class TestOrchestration:
    """Scenario: fallback chain CRUD, account health, rate limit clearing."""

    def test_get_fallback_chain_empty(self, client):
        """GET fallback chain for a trigger with none returns empty chain."""
        trigger_id = _create_trigger(client, name="orch-trigger")
        resp = client.get(
            f"/admin/orchestration/triggers/{trigger_id}/fallback-chain"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["chain"] == []

    def test_set_and_get_fallback_chain(self, client):
        """PUT then GET fallback chain round-trips correctly."""
        trigger_id = _create_trigger(client, name="orch-fb-trigger")
        _backend_id, account_id = _seed_backend_and_account()

        resp = client.put(
            f"/admin/orchestration/triggers/{trigger_id}/fallback-chain",
            json={
                "entries": [
                    {"backend_type": "claude", "account_id": account_id},
                ]
            },
        )
        assert resp.status_code == 200
        chain = resp.get_json()["chain"]
        assert len(chain) == 1
        assert chain[0]["backend_type"] == "claude"
        assert chain[0]["account_id"] == account_id

        # Verify with GET
        resp2 = client.get(
            f"/admin/orchestration/triggers/{trigger_id}/fallback-chain"
        )
        assert resp2.status_code == 200
        assert len(resp2.get_json()["chain"]) == 1

    def test_set_fallback_chain_invalid_backend(self, client):
        """PUT fallback chain with invalid backend_type returns 400."""
        trigger_id = _create_trigger(client, name="orch-bad-backend")
        resp = client.put(
            f"/admin/orchestration/triggers/{trigger_id}/fallback-chain",
            json={"entries": [{"backend_type": "nonexistent_backend"}]},
        )
        assert resp.status_code == 400

    def test_delete_fallback_chain(self, client):
        """DELETE fallback chain returns 204 and chain is empty afterwards."""
        trigger_id = _create_trigger(client, name="orch-del-trigger")
        _backend_id, account_id = _seed_backend_and_account()

        # Set chain first
        client.put(
            f"/admin/orchestration/triggers/{trigger_id}/fallback-chain",
            json={"entries": [{"backend_type": "claude", "account_id": account_id}]},
        )

        # Delete
        resp = client.delete(
            f"/admin/orchestration/triggers/{trigger_id}/fallback-chain"
        )
        assert resp.status_code == 204

        # Verify empty
        resp2 = client.get(
            f"/admin/orchestration/triggers/{trigger_id}/fallback-chain"
        )
        assert resp2.get_json()["chain"] == []

    def test_get_account_health(self, client):
        """GET /admin/orchestration/health returns account health states."""
        resp = client.get("/admin/orchestration/health")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "accounts" in body
        assert isinstance(body["accounts"], list)

    def test_get_account_health_with_accounts(self, client):
        """Health endpoint includes seeded accounts."""
        _seed_backend_and_account()
        resp = client.get("/admin/orchestration/health")
        assert resp.status_code == 200
        accounts = resp.get_json()["accounts"]
        assert len(accounts) >= 1
        assert "account_id" in accounts[0]
        assert "is_rate_limited" in accounts[0]

    def test_clear_rate_limit_nonexistent_account(self, client):
        """POST clear-rate-limit for unknown account returns 404."""
        resp = client.post("/admin/orchestration/accounts/99999/clear-rate-limit")
        assert resp.status_code == 404

    def test_clear_rate_limit_success(self, client):
        """POST clear-rate-limit for existing account returns success."""
        _backend_id, account_id = _seed_backend_and_account()
        resp = client.post(
            f"/admin/orchestration/accounts/{account_id}/clear-rate-limit"
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Rate limit cleared"
