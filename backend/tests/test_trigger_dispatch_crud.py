import pytest
from app.db import triggers as trigger_db


class TestTriggerDispatchCrud:
    def test_create_trigger_with_dispatch_type(self, isolated_db):
        tid = trigger_db.create_trigger(
            name="sa-trigger",
            prompt_template="run {message}",
            dispatch_type="super_agent",
            super_agent_id="sa-abc123",
        )
        assert tid is not None
        t = trigger_db.get_trigger(tid)
        assert t["dispatch_type"] == "super_agent"
        assert t["super_agent_id"] == "sa-abc123"

    def test_create_trigger_defaults_to_bot(self, isolated_db):
        tid = trigger_db.create_trigger(
            name="bot-trigger",
            prompt_template="run {message}",
        )
        t = trigger_db.get_trigger(tid)
        assert t["dispatch_type"] == "bot"
        assert t["super_agent_id"] is None

    def test_update_trigger_dispatch_type(self, isolated_db):
        tid = trigger_db.create_trigger(
            name="update-test",
            prompt_template="run {message}",
        )
        result = trigger_db.update_trigger(
            tid, dispatch_type="super_agent", super_agent_id="sa-xyz789"
        )
        assert result is True
        t = trigger_db.get_trigger(tid)
        assert t["dispatch_type"] == "super_agent"
        assert t["super_agent_id"] == "sa-xyz789"
