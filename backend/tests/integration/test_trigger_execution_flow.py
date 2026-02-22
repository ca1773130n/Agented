"""Integration tests for trigger CRUD operations and frontend contract validation.

These tests use the Flask test client with isolated_db -- NO mocking of database
or service layer. They verify that API response JSON field names match the
frontend TypeScript interface definitions in frontend/src/services/api/types.ts.

Reference: The Trigger interface in types.ts defines the contract that the
frontend expects from GET /admin/triggers responses.
"""

from tests.integration.conftest import assert_response_contract

# ---------------------------------------------------------------------------
# Reference field sets derived from frontend/src/services/api/types.ts
# ---------------------------------------------------------------------------

# From the Trigger interface in types.ts (required fields only)
TRIGGER_REQUIRED_FIELDS = {
    "id",
    "name",
    "prompt_template",
    "backend_type",
    "trigger_source",
    "detection_keyword",
    "group_id",
    "is_predefined",
    "enabled",
    "auto_resolve",
    "created_at",
}

# Wrapper response for GET /admin/triggers
TRIGGER_LIST_RESPONSE_FIELDS = {"triggers"}


# ---------------------------------------------------------------------------
# Trigger list endpoint tests
# ---------------------------------------------------------------------------


def test_list_triggers_returns_200(client, isolated_db):
    """GET /admin/triggers returns 200."""
    resp = client.get("/admin/triggers")
    assert resp.status_code == 200


def test_list_triggers_response_has_triggers_key(client, isolated_db):
    """GET /admin/triggers response JSON has 'triggers' key."""
    resp = client.get("/admin/triggers")
    data = resp.get_json()
    assert_response_contract(data, TRIGGER_LIST_RESPONSE_FIELDS, "TriggerListResponse")


def test_list_triggers_contains_predefined(client, isolated_db):
    """GET /admin/triggers response contains at least 2 predefined triggers."""
    resp = client.get("/admin/triggers")
    data = resp.get_json()
    triggers = data["triggers"]
    assert len(triggers) >= 2, (
        f"Expected at least 2 predefined triggers (bot-security, bot-pr-review), "
        f"got {len(triggers)}"
    )


def test_trigger_fields_match_frontend_contract(client, isolated_db):
    """Each trigger in the list has all TRIGGER_REQUIRED_FIELDS from frontend types.ts."""
    resp = client.get("/admin/triggers")
    data = resp.get_json()
    triggers = data["triggers"]
    assert len(triggers) >= 1, "No triggers returned"

    for trigger in triggers:
        assert_response_contract(trigger, TRIGGER_REQUIRED_FIELDS, f"Trigger[{trigger.get('id')}]")


# ---------------------------------------------------------------------------
# Trigger detail endpoint tests
# ---------------------------------------------------------------------------


def test_get_trigger_detail_returns_200(client, isolated_db):
    """GET /admin/triggers/bot-security returns 200."""
    resp = client.get("/admin/triggers/bot-security")
    assert resp.status_code == 200


def test_get_trigger_detail_fields(client, isolated_db):
    """GET /admin/triggers/bot-security detail response has all TRIGGER_REQUIRED_FIELDS."""
    resp = client.get("/admin/triggers/bot-security")
    data = resp.get_json()
    assert_response_contract(data, TRIGGER_REQUIRED_FIELDS, "TriggerDetail[bot-security]")


def test_get_nonexistent_trigger_returns_404(client, isolated_db):
    """GET /admin/triggers/nonexistent returns 404."""
    resp = client.get("/admin/triggers/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Trigger CRUD cycle tests
# ---------------------------------------------------------------------------


def test_create_trigger_and_retrieve(client, isolated_db):
    """POST /admin/triggers -> GET the created trigger, verify fields match."""
    create_payload = {
        "name": "Integration Test Trigger",
        "prompt_template": "Run integration test: {message}",
        "backend_type": "claude",
        "trigger_source": "manual",
        "detection_keyword": "test",
    }
    create_resp = client.post("/admin/triggers", json=create_payload)
    assert create_resp.status_code == 201, f"Create failed: {create_resp.get_json()}"

    create_data = create_resp.get_json()
    trigger_id = create_data["trigger_id"]

    # Retrieve the created trigger
    get_resp = client.get(f"/admin/triggers/{trigger_id}")
    assert get_resp.status_code == 200

    trigger = get_resp.get_json()
    assert_response_contract(trigger, TRIGGER_REQUIRED_FIELDS, f"CreatedTrigger[{trigger_id}]")
    assert trigger["name"] == "Integration Test Trigger"
    assert trigger["prompt_template"] == "Run integration test: {message}"
    assert trigger["backend_type"] == "claude"


def test_update_trigger_persists(client, isolated_db):
    """Create a trigger, PUT to update name, GET to verify updated name."""
    # Create
    create_resp = client.post(
        "/admin/triggers",
        json={
            "name": "Original Name",
            "prompt_template": "Test prompt",
            "backend_type": "claude",
            "trigger_source": "manual",
        },
    )
    assert create_resp.status_code == 201
    trigger_id = create_resp.get_json()["trigger_id"]

    # Update
    update_resp = client.put(
        f"/admin/triggers/{trigger_id}",
        json={"name": "Updated Name"},
    )
    assert update_resp.status_code == 200

    # Verify
    get_resp = client.get(f"/admin/triggers/{trigger_id}")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["name"] == "Updated Name"


def test_delete_trigger_removes_it(client, isolated_db):
    """Create a non-predefined trigger, DELETE it, GET returns 404."""
    # Create
    create_resp = client.post(
        "/admin/triggers",
        json={
            "name": "To Be Deleted",
            "prompt_template": "Delete me",
            "backend_type": "claude",
            "trigger_source": "manual",
        },
    )
    assert create_resp.status_code == 201
    trigger_id = create_resp.get_json()["trigger_id"]

    # Delete
    delete_resp = client.delete(f"/admin/triggers/{trigger_id}")
    assert delete_resp.status_code == 200

    # Verify it is gone
    get_resp = client.get(f"/admin/triggers/{trigger_id}")
    assert get_resp.status_code == 404
