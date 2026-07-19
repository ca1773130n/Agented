"""Regression tests for autofix Tier-2 status integrity."""

import app.services.autofix_service as af
import app.services.streaming_helper as sh
import app.services.super_agent_session_service as sass
from app.models.system import ErrorStatus


def test_tier2_investigation_does_not_self_heal_to_fixed(monkeypatch):
    """A Tier-2 agent investigation completing its stream — even with empty output —
    must NOT flip the system error to FIXED. There is no verification that the agent
    actually fixed anything (and it leaves changes uncommitted), so unconditionally
    marking FIXED hid still-recurring errors from the operator. It must stay
    INVESTIGATING for review. Regression for the hardening-audit HIGH finding.
    """
    status_calls: list[str] = []
    monkeypatch.setattr(af, "update_system_error_status", lambda eid, status: status_calls.append(status))
    monkeypatch.setattr(af, "update_fix_attempt", lambda *a, **k: None)

    class _FakeSession:
        @staticmethod
        def get_or_create_session(_):
            return "sess-1"

        @staticmethod
        def send_message(*a, **k):
            return None

    monkeypatch.setattr(sass, "SuperAgentSessionService", _FakeSession)

    # Simulate the stream finishing normally -> fires on_complete (the buggy path).
    def _fake_run(session_id, super_agent_id, backend, on_complete, on_error):
        on_complete()

    monkeypatch.setattr(sh, "run_streaming_response", _fake_run)

    af._run_tier2_investigation(
        "err-1", "fix-1", {"id": "err-1", "category": "x", "message": "boom"}
    )

    assert ErrorStatus.FIXED.value not in status_calls, (
        "Tier-2 investigation must not self-heal the error to FIXED without verification"
    )
    assert status_calls == [ErrorStatus.INVESTIGATING.value]
