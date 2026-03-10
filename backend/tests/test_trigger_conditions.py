"""Tests for trigger condition rules (conditional trigger filtering)."""

import json
import pytest


class TestTriggerConditionsDB:
    """Unit tests for trigger_conditions DB functions."""

    def test_create_and_list(self, isolated_db):
        from app.db.trigger_conditions import create_trigger_condition, list_trigger_conditions

        cid = create_trigger_condition(
            trigger_id="bot-security",
            name="Main Branch Only",
            description="Only run on main",
            enabled=True,
            logic="AND",
            conditions=[{"id": "c1", "field": "pr.base_branch", "operator": "equals", "value": "main"}],
        )
        assert cid is not None
        assert cid.startswith("tcond-")

        rules = list_trigger_conditions("bot-security")
        assert len(rules) == 1
        rule = rules[0]
        assert rule["name"] == "Main Branch Only"
        assert rule["logic"] == "AND"
        assert rule["enabled"] == 1
        assert len(rule["conditions"]) == 1
        assert rule["conditions"][0]["field"] == "pr.base_branch"

    def test_list_empty_for_unknown_trigger(self, isolated_db):
        from app.db.trigger_conditions import list_trigger_conditions

        rules = list_trigger_conditions("nonexistent-trigger")
        assert rules == []

    def test_get_by_id(self, isolated_db):
        from app.db.trigger_conditions import create_trigger_condition, get_trigger_condition

        cid = create_trigger_condition(
            trigger_id="bot-pr-review",
            name="Large PRs",
            conditions=[{"id": "c1", "field": "pr.lines_changed", "operator": "greater_than", "value": "200"}],
        )
        rule = get_trigger_condition(cid)
        assert rule is not None
        assert rule["id"] == cid
        assert rule["trigger_id"] == "bot-pr-review"

    def test_get_nonexistent_returns_none(self, isolated_db):
        from app.db.trigger_conditions import get_trigger_condition

        assert get_trigger_condition("tcond-doesnotexist") is None

    def test_update_condition(self, isolated_db):
        from app.db.trigger_conditions import (
            create_trigger_condition,
            get_trigger_condition,
            update_trigger_condition,
        )

        cid = create_trigger_condition(
            trigger_id="bot-security",
            name="Old Name",
            enabled=True,
            logic="AND",
            conditions=[],
        )
        ok = update_trigger_condition(
            cid,
            name="New Name",
            enabled=False,
            logic="OR",
            conditions=[{"id": "c1", "field": "pr.author", "operator": "equals", "value": "bot"}],
        )
        assert ok is True
        rule = get_trigger_condition(cid)
        assert rule["name"] == "New Name"
        assert rule["enabled"] == 0
        assert rule["logic"] == "OR"
        assert len(rule["conditions"]) == 1

    def test_update_nonexistent_returns_false(self, isolated_db):
        from app.db.trigger_conditions import update_trigger_condition

        ok = update_trigger_condition("tcond-ghost", name="whatever")
        assert ok is False

    def test_delete_condition(self, isolated_db):
        from app.db.trigger_conditions import (
            create_trigger_condition,
            delete_trigger_condition,
            get_trigger_condition,
        )

        cid = create_trigger_condition(trigger_id="bot-security", name="To Delete", conditions=[])
        assert get_trigger_condition(cid) is not None

        ok = delete_trigger_condition(cid)
        assert ok is True
        assert get_trigger_condition(cid) is None

    def test_delete_nonexistent_returns_false(self, isolated_db):
        from app.db.trigger_conditions import delete_trigger_condition

        assert delete_trigger_condition("tcond-ghost") is False

    def test_conditions_json_roundtrip(self, isolated_db):
        """Conditions list is JSON-serialized to DB and deserialized on read."""
        from app.db.trigger_conditions import create_trigger_condition, get_trigger_condition

        conditions = [
            {"id": "c1", "field": "file.path", "operator": "matches", "value": "src/**"},
            {"id": "c2", "field": "pr.author", "operator": "not_equals", "value": "dependabot"},
        ]
        cid = create_trigger_condition(
            trigger_id="bot-security",
            name="Complex Rule",
            conditions=conditions,
        )
        rule = get_trigger_condition(cid)
        assert rule["conditions"] == conditions


class TestTriggerConditionsAPI:
    """Integration tests for trigger conditions REST API."""

    def test_list_conditions_empty(self, client):
        response = client.get("/admin/triggers/bot-security/conditions")
        assert response.status_code == 200
        data = response.get_json()
        assert data["rules"] == []
        assert data["total"] == 0

    def test_create_condition(self, client):
        payload = {
            "name": "Main Branch Only",
            "description": "Filter to main",
            "enabled": True,
            "logic": "AND",
            "conditions": [
                {"id": "c1", "field": "pr.base_branch", "operator": "equals", "value": "main"}
            ],
        }
        response = client.post(
            "/admin/triggers/bot-security/conditions",
            json=payload,
            content_type="application/json",
        )
        assert response.status_code == 201
        data = response.get_json()
        assert "rule" in data
        assert data["rule"]["name"] == "Main Branch Only"
        assert data["rule"]["id"].startswith("tcond-")

    def test_create_then_list(self, client):
        client.post(
            "/admin/triggers/bot-pr-review/conditions",
            json={"name": "Rule A", "conditions": []},
            content_type="application/json",
        )
        client.post(
            "/admin/triggers/bot-pr-review/conditions",
            json={"name": "Rule B", "conditions": []},
            content_type="application/json",
        )
        resp = client.get("/admin/triggers/bot-pr-review/conditions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 2

    def test_get_condition_not_found(self, client):
        resp = client.get("/admin/trigger-conditions/tcond-doesnotexist")
        assert resp.status_code == 404

    def test_update_condition(self, client):
        create_resp = client.post(
            "/admin/triggers/bot-security/conditions",
            json={"name": "Old Name", "conditions": []},
            content_type="application/json",
        )
        cid = create_resp.get_json()["rule"]["id"]

        update_resp = client.put(
            f"/admin/trigger-conditions/{cid}",
            json={"name": "New Name", "enabled": False},
            content_type="application/json",
        )
        assert update_resp.status_code == 200
        data = update_resp.get_json()
        assert data["name"] == "New Name"
        assert data["enabled"] == 0

    def test_delete_condition(self, client):
        create_resp = client.post(
            "/admin/triggers/bot-security/conditions",
            json={"name": "To Delete", "conditions": []},
            content_type="application/json",
        )
        cid = create_resp.get_json()["rule"]["id"]

        del_resp = client.delete(f"/admin/trigger-conditions/{cid}")
        assert del_resp.status_code == 200

        get_resp = client.get(f"/admin/trigger-conditions/{cid}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/admin/trigger-conditions/tcond-ghost")
        assert resp.status_code == 404
