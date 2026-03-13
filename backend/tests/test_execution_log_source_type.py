import pytest
from datetime import datetime
from app.db import triggers as trigger_db


class TestExecutionLogSourceType:
    def _create_trigger(self):
        return trigger_db.create_trigger(
            name="test-trigger", prompt_template="test"
        )

    def test_create_log_with_source_type(self, isolated_db):
        tid = self._create_trigger()
        eid = "exec-001"
        result = trigger_db.create_execution_log(
            execution_id=eid,
            trigger_id=tid,
            trigger_type="webhook",
            started_at=datetime.utcnow().isoformat(),
            prompt="test prompt",
            backend_type="claude",
            command="claude -p test",
            source_type="super_agent",
            session_id="sess-abc123",
        )
        assert result is True
        log = trigger_db.get_execution_log(eid)
        assert log["source_type"] == "super_agent"
        assert log["session_id"] == "sess-abc123"

    def test_create_log_defaults_to_bot(self, isolated_db):
        tid = self._create_trigger()
        eid = "exec-002"
        trigger_db.create_execution_log(
            execution_id=eid,
            trigger_id=tid,
            trigger_type="webhook",
            started_at=datetime.utcnow().isoformat(),
            prompt="test",
            backend_type="claude",
            command="claude -p test",
        )
        log = trigger_db.get_execution_log(eid)
        assert log["source_type"] == "bot"
        assert log["session_id"] is None

    def test_create_log_with_null_trigger_id_for_user_chat(self, isolated_db):
        eid = "exec-003"
        result = trigger_db.create_execution_log(
            execution_id=eid,
            trigger_id=None,
            trigger_type="user_chat",
            started_at=datetime.utcnow().isoformat(),
            prompt="user chat prompt",
            backend_type="claude",
            command="",
            source_type="user_chat",
            session_id="sess-xyz",
        )
        assert result is True
        log = trigger_db.get_execution_log(eid)
        assert log["source_type"] == "user_chat"
        assert log["trigger_id"] is None
