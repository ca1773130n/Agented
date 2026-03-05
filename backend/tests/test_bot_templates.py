"""Tests for bot template CRUD and deploy operations."""

from app.db.bot_templates import CURATED_BOT_TEMPLATES, get_all_templates, get_template
from app.db.seeds import seed_bot_templates


def _seed_templates():
    """Seed bot templates (not done by default isolated_db fixture)."""
    seed_bot_templates()


def test_curated_templates_seeded(isolated_db):
    """After seeding, verify 5 templates exist with correct slugs."""
    _seed_templates()
    templates = get_all_templates()
    assert len(templates) == 5
    slugs = {t["slug"] for t in templates}
    expected = {"pr-reviewer", "dependency-updater", "security-scanner",
                "changelog-generator", "test-writer"}
    assert slugs == expected


def test_list_templates_endpoint(client):
    """GET /admin/bot-templates returns 200 with 5 templates."""
    _seed_templates()
    resp = client.get("/admin/bot-templates/")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["templates"]) == 5


def test_get_template_by_id(client):
    """GET /admin/bot-templates/{id} returns correct template."""
    _seed_templates()
    templates = get_all_templates()
    template = templates[0]
    resp = client.get(f"/admin/bot-templates/{template['id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["slug"] == template["slug"]
    assert data["name"] == template["name"]


def test_deploy_template_creates_trigger(client):
    """POST /admin/bot-templates/{id}/deploy returns 201 with trigger_id."""
    _seed_templates()
    templates = get_all_templates()
    template = templates[0]

    resp = client.post(f"/admin/bot-templates/{template['id']}/deploy")
    assert resp.status_code == 201
    data = resp.get_json()
    assert "trigger_id" in data
    trigger_id = data["trigger_id"]

    # Verify trigger exists
    from app.db.triggers import get_trigger
    trigger = get_trigger(trigger_id)
    assert trigger is not None
    assert trigger["name"] is not None


def test_deploy_same_template_twice_creates_unique_name(client):
    """Deploy same template twice; second trigger should have ' (2)' suffix."""
    _seed_templates()
    templates = get_all_templates()
    template = templates[0]

    resp1 = client.post(f"/admin/bot-templates/{template['id']}/deploy")
    assert resp1.status_code == 201
    data1 = resp1.get_json()

    resp2 = client.post(f"/admin/bot-templates/{template['id']}/deploy")
    assert resp2.status_code == 201
    data2 = resp2.get_json()

    from app.db.triggers import get_trigger
    trigger1 = get_trigger(data1["trigger_id"])
    trigger2 = get_trigger(data2["trigger_id"])

    # Second deployment should have (2) suffix
    assert trigger1["name"] != trigger2["name"]
    assert "(2)" in trigger2["name"]


def test_deploy_nonexistent_template(client):
    """POST with invalid ID returns 404."""
    resp = client.post("/admin/bot-templates/nonexistent-id/deploy")
    assert resp.status_code == 404
