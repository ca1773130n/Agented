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
    monkeypatch.setattr(
        af, "update_system_error_status", lambda eid, status: status_calls.append(status)
    )
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


# ---------- which backend Tier-2 spends on ---------------------------------


def _run_tier2_capturing_backend(monkeypatch) -> str:
    """Drive one Tier-2 investigation and return the backend it launched."""
    monkeypatch.setattr(af, "update_system_error_status", lambda eid, status: None)
    monkeypatch.setattr(af, "update_fix_attempt", lambda *a, **k: None)

    class _FakeSession:
        @staticmethod
        def get_or_create_session(_):
            return "sess-1"

        @staticmethod
        def send_message(*a, **k):
            return None

    monkeypatch.setattr(sass, "SuperAgentSessionService", _FakeSession)

    seen: list[str] = []

    def _fake_run(session_id, super_agent_id, backend, on_complete, on_error):
        seen.append(backend)
        on_complete()

    monkeypatch.setattr(sh, "run_streaming_response", _fake_run)
    af._run_tier2_investigation(
        "err-1", "fix-1", {"id": "err-1", "category": "x", "message": "boom"}
    )
    return seen[0]


def test_tier2_defaults_to_codex(monkeypatch):
    """Tier-2 used to hardcode claude, which made autofix the one LLM feature that
    ignored the operator's backend — while spending tokens unattended."""
    monkeypatch.setattr(af, "get_setting", lambda key: None)
    assert _run_tier2_capturing_backend(monkeypatch) == "codex"


def test_tier2_honours_the_configured_backend(monkeypatch):
    monkeypatch.setattr(af, "get_setting", lambda key: "  OpenCode  ")
    assert _run_tier2_capturing_backend(monkeypatch) == "opencode"


def test_tier2_falls_back_rather_than_launching_an_unknown_backend(monkeypatch):
    """A typo in the setting must not reach the spawner as a backend name."""
    monkeypatch.setattr(af, "get_setting", lambda key: "claud")
    assert _run_tier2_capturing_backend(monkeypatch) == "codex"


def test_tier2_survives_an_unreadable_settings_table(monkeypatch):
    """capture_error() runs on the error path; a failing settings read here must
    not turn one error into two."""

    def _boom(key):
        raise RuntimeError("no such table: settings")

    monkeypatch.setattr(af, "get_setting", _boom)
    assert _run_tier2_capturing_backend(monkeypatch) == "codex"
