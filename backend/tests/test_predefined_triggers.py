"""Tests for predefined trigger registration and protection."""


def test_both_predefined_triggers_are_seeded(client):
    """Both bot-security and bot-pr-review must exist after startup."""
    resp = client.get("/admin/triggers/")
    assert resp.status_code == 200
    triggers = resp.get_json()["triggers"]
    ids = [t["id"] for t in triggers]
    assert "bot-security" in ids
    assert "bot-pr-review" in ids


def test_predefined_triggers_are_marked_predefined(client):
    """Predefined triggers should have is_predefined = 1."""
    for trigger_id in ("bot-security", "bot-pr-review"):
        resp = client.get(f"/admin/triggers/{trigger_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_predefined"] == 1


def test_security_trigger_cannot_be_deleted(client):
    """Attempting to delete bot-security should return 403."""
    resp = client.delete("/admin/triggers/bot-security")
    assert resp.status_code == 403


def test_pr_review_trigger_cannot_be_deleted(client):
    """Attempting to delete bot-pr-review should return 403."""
    resp = client.delete("/admin/triggers/bot-pr-review")
    assert resp.status_code == 403


def test_pr_review_trigger_properties(client):
    """bot-pr-review should have the expected default properties."""
    resp = client.get("/admin/triggers/bot-pr-review")
    assert resp.status_code == 200
    trigger = resp.get_json()
    assert trigger["name"] == "PR Review"
    assert trigger["backend_type"] == "claude"
    assert trigger["trigger_source"] == "github"
    assert trigger["is_predefined"] == 1
    assert trigger["enabled"] == 1


def test_security_trigger_properties(client):
    """bot-security should keep its expected properties."""
    resp = client.get("/admin/triggers/bot-security")
    assert resp.status_code == 200
    trigger = resp.get_json()
    assert trigger["name"] == "Weekly Security Audit"
    assert trigger["trigger_source"] == "webhook"
    assert trigger["is_predefined"] == 1


def test_predefined_triggers_have_correct_trigger_sources(client):
    """Each predefined trigger should have the correct trigger source."""
    resp = client.get("/admin/triggers/")
    assert resp.status_code == 200
    triggers = {t["id"]: t for t in resp.get_json()["triggers"]}

    # bot-security uses JSON webhooks
    assert triggers["bot-security"]["trigger_source"] == "webhook"

    # bot-pr-review uses GitHub webhooks
    assert triggers["bot-pr-review"]["trigger_source"] == "github"
