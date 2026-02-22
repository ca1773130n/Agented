"""Integration tests for execution history endpoints.

These tests cover the specific API path that caused the production 500 error:
GET /admin/triggers/bot-pr-review/executions

The tests use Flask test client with isolated_db -- NO mocking. Response field
validation uses separate field sets for trigger-scoped vs all-executions endpoints
because they use different SQL queries:

- Trigger-scoped (GET /admin/triggers/{id}/executions): SELECT * on execution_logs
  WITHOUT a JOIN, so trigger_name is NOT present.
- All-executions (GET /admin/executions): SELECT e.*, t.name as trigger_name via
  LEFT JOIN triggers, so trigger_name IS present.

Reference: frontend/src/services/api/types.ts Execution interface.
"""

from tests.integration.conftest import assert_response_contract

# ---------------------------------------------------------------------------
# Reference field sets derived from frontend/src/services/api/types.ts
# ---------------------------------------------------------------------------

# Fields present in trigger-scoped execution history (SELECT * on execution_logs -- no JOIN)
# "id" is the INTEGER PRIMARY KEY from execution_logs table, required by frontend Execution interface
EXECUTION_FIELDS_TRIGGER_SCOPED = {
    "id",
    "execution_id",
    "trigger_id",
    "trigger_type",
    "backend_type",
    "status",
    "started_at",
}

# Fields present in all-executions response (SELECT e.*, t.name as trigger_name via LEFT JOIN)
# "id" is the INTEGER PRIMARY KEY from execution_logs table, required by frontend Execution interface
EXECUTION_FIELDS_ALL = {
    "id",
    "execution_id",
    "trigger_id",
    "trigger_name",
    "trigger_type",
    "backend_type",
    "status",
    "started_at",
}

# Wrapper response fields
EXECUTION_LIST_RESPONSE_FIELDS = {"executions", "total"}


# ---------------------------------------------------------------------------
# Trigger-scoped execution history (THE PRODUCTION 500-ERROR PATH)
# ---------------------------------------------------------------------------


def test_trigger_executions_returns_200(client, isolated_db):
    """GET /admin/triggers/bot-pr-review/executions returns 200.

    THIS IS THE EXACT PATH THAT CAUSED THE PRODUCTION 500 ERROR.
    """
    resp = client.get("/admin/triggers/bot-pr-review/executions")
    assert resp.status_code == 200


def test_trigger_executions_returns_200_for_security(client, isolated_db):
    """GET /admin/triggers/bot-security/executions returns 200."""
    resp = client.get("/admin/triggers/bot-security/executions")
    assert resp.status_code == 200


def test_trigger_executions_response_structure(client, isolated_db):
    """Trigger-scoped execution response has expected top-level keys."""
    resp = client.get("/admin/triggers/bot-security/executions")
    data = resp.get_json()
    assert "executions" in data, f"Missing 'executions' key. Got: {sorted(data.keys())}"
    assert (
        "running_execution" in data
    ), f"Missing 'running_execution' key. Got: {sorted(data.keys())}"
    assert "total" in data, f"Missing 'total' key. Got: {sorted(data.keys())}"


def test_trigger_executions_with_data(client, isolated_db, seed_test_execution):
    """Trigger-scoped executions with seeded data returns correct fields.

    Uses EXECUTION_FIELDS_TRIGGER_SCOPED (NOT _ALL) because this endpoint
    uses SELECT * without JOIN -- trigger_name is not present.
    """
    resp = client.get("/admin/triggers/bot-security/executions")
    assert resp.status_code == 200

    data = resp.get_json()
    executions = data["executions"]
    assert len(executions) >= 1, "Expected at least 1 seeded execution"

    for execution in executions:
        assert_response_contract(
            execution,
            EXECUTION_FIELDS_TRIGGER_SCOPED,
            "TriggerScopedExecution",
        )


def test_nonexistent_trigger_executions_returns_404(client, isolated_db):
    """GET /admin/triggers/nonexistent/executions returns 404."""
    resp = client.get("/admin/triggers/nonexistent/executions")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# All-executions endpoint
# ---------------------------------------------------------------------------


def test_all_executions_returns_200(client, isolated_db):
    """GET /admin/executions returns 200."""
    resp = client.get("/admin/executions")
    assert resp.status_code == 200


def test_all_executions_response_structure(client, isolated_db):
    """All-executions response has 'executions' and 'total' keys."""
    resp = client.get("/admin/executions")
    data = resp.get_json()
    assert_response_contract(data, EXECUTION_LIST_RESPONSE_FIELDS, "AllExecutionsResponse")


def test_all_executions_with_data_includes_trigger_name(client, isolated_db, seed_test_execution):
    """All-executions endpoint includes trigger_name from LEFT JOIN.

    Uses EXECUTION_FIELDS_ALL (which includes trigger_name) because
    get_all_execution_logs() does a LEFT JOIN triggers to add trigger_name.
    """
    resp = client.get("/admin/executions")
    assert resp.status_code == 200

    data = resp.get_json()
    executions = data["executions"]
    assert len(executions) >= 1, "Expected at least 1 seeded execution"

    for execution in executions:
        assert_response_contract(
            execution,
            EXECUTION_FIELDS_ALL,
            "AllExecution",
        )


# ---------------------------------------------------------------------------
# Single execution detail
# ---------------------------------------------------------------------------


def test_single_execution_detail(client, isolated_db, seed_test_execution):
    """GET /admin/executions/exec-test-001 returns correct fields.

    Single execution detail also uses SELECT * without JOIN, so trigger_name
    is NOT present -- use EXECUTION_FIELDS_TRIGGER_SCOPED.
    """
    resp = client.get("/admin/executions/exec-test-001")
    assert resp.status_code == 200

    data = resp.get_json()
    assert_response_contract(
        data,
        EXECUTION_FIELDS_TRIGGER_SCOPED,
        "ExecutionDetail[exec-test-001]",
    )


def test_nonexistent_execution_returns_404(client, isolated_db):
    """GET /admin/executions/nonexistent returns 404."""
    resp = client.get("/admin/executions/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_execution_history_pagination(client, isolated_db):
    """GET /admin/triggers/bot-security/executions?limit=5&offset=0 returns 200."""
    resp = client.get("/admin/triggers/bot-security/executions?limit=5&offset=0")
    assert resp.status_code == 200

    data = resp.get_json()
    assert "executions" in data
    assert isinstance(data["executions"], list)
