"""Integration test for the chat rate-limit rotation loop in
streaming_helper.run_streaming_response.

Stubs the CLI runner so one account yields a RateLimitEvent and the next
yields real content, then asserts the turn rotated, marked the limited
account, and finished on the fallback account."""

from __future__ import annotations

import os

import pytest

from app.services.account_rotation_service import RateLimitEvent, RateLimitInfo


@pytest.fixture
def two_claude_accounts(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute("SELECT id FROM ai_backends WHERE type='claude' LIMIT 1").fetchone()
        if row:
            backend_id = row[0]
        else:
            backend_id = "rot-claude"
            conn.execute(
                "INSERT INTO ai_backends (id, type, name, is_installed) VALUES (?,?,?,1)",
                (backend_id, "claude", "Claude"),
            )
        conn.execute("DELETE FROM backend_accounts WHERE backend_id=?", (backend_id,))
        for name, cfg, is_def in [
            ("Personal1", "~/.claude-personal1", 1),
            ("Personal2", "~/.claude-personal2", 0),
        ]:
            conn.execute(
                "INSERT INTO backend_accounts (backend_id, account_name, config_path, is_default) "
                "VALUES (?,?,?,?)",
                (backend_id, name, cfg, is_def),
            )
        conn.commit()
    return isolated_db


def _install_common_stubs(monkeypatch, deltas):
    """Stub the streaming chokepoint's collaborators so only the rotation
    logic is exercised. Captures ChatStateService deltas into `deltas`."""
    import app.services.streaming_helper as sh
    from app.services import cli_agent_runner_service as runner

    # Run the streaming "thread" synchronously.
    class _SyncThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(sh.threading, "Thread", _SyncThread)

    # ChatStateService capture.
    monkeypatch.setattr(sh.ChatStateService, "init_session", lambda *a, **k: None)
    monkeypatch.setattr(sh.ChatStateService, "push_status", lambda *a, **k: None)
    monkeypatch.setattr(
        sh.ChatStateService,
        "push_delta",
        lambda sid, kind, payload: deltas.append((kind, payload)),
    )

    # Session service: minimal system prompt + empty log; capture saved msg.
    saved = {}
    monkeypatch.setattr(
        sh.SuperAgentSessionService, "assemble_system_prompt", lambda *a, **k: "SYS"
    )
    monkeypatch.setattr(
        sh.SuperAgentSessionService, "get_session_state", lambda *a, **k: {"conversation_log": []}
    )
    monkeypatch.setattr(
        sh.SuperAgentSessionService,
        "add_assistant_message",
        lambda sid, content, backend=None: saved.update(content=content, backend=backend),
    )

    # Force the CLI-agent path.
    monkeypatch.setattr(runner, "should_route_via_cli_agent", lambda *a, **k: True)
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: False)
    return saved


def test_rotates_to_next_account_on_rate_limit(monkeypatch, two_claude_accounts):
    from app.services import cli_agent_runner_service as runner
    from app.services import streaming_helper as sh
    from app.services.rate_limit_service import RateLimitService
    from app.db.backends import get_accounts_for_backend_type

    deltas: list = []
    saved = _install_common_stubs(monkeypatch, deltas)

    p1_cfg = os.path.expanduser("~/.claude-personal1")
    p2_cfg = os.path.expanduser("~/.claude-personal2")

    # Personal1 (requested/default) rate-limits; Personal2 answers.
    def fake_stream(messages, *, backend, cwd, yolo, model, config_dir):
        if config_dir == p1_cfg:
            yield RateLimitEvent(
                RateLimitInfo(reason="You've hit your weekly limit · resets Jun 12 at 6am")
            )
        else:
            yield "Hello "
            yield "from Personal2"

    monkeypatch.setattr(runner, "stream_via_cli_agent", fake_stream)
    # Requested account resolves to Personal1's config.
    monkeypatch.setattr(runner, "resolve_account_config_dir", lambda aid, backend: p1_cfg)

    sh.run_streaming_response(
        session_id="sess-1",
        super_agent_id="psa-1",
        backend="claude",
        account_id=None,
    )

    kinds = [k for k, _ in deltas]
    # Rotated exactly once, finished with Personal2's content.
    assert "rotation" in kinds, deltas
    rot = next(p for k, p in deltas if k == "rotation")
    assert rot["from"] == "Personal1"
    assert rot["to"] == "Personal2"
    assert "weekly limit" in rot["reason"]

    assert saved.get("content") == "Hello from Personal2"
    finish = next(p for k, p in deltas if k == "finish")
    assert finish["content"] == "Hello from Personal2"

    # Personal1 was marked rate-limited; Personal2 was not.
    accts = {a["account_name"]: a for a in get_accounts_for_backend_type("claude")}
    assert RateLimitService.is_rate_limited(accts["Personal1"]["id"]) is True
    assert RateLimitService.is_rate_limited(accts["Personal2"]["id"]) is False


def test_all_accounts_rate_limited_queues_the_turn(monkeypatch, two_claude_accounts):
    """Phase 2: exhaustion parks the turn in the retry queue and emits a
    `queued` delta instead of a hard error."""
    from app.db import chat_retry_queue as q
    from app.services import cli_agent_runner_service as runner
    from app.services import streaming_helper as sh

    deltas: list = []
    _install_common_stubs(monkeypatch, deltas)

    # Both accounts rate-limit.
    def fake_stream(messages, *, backend, cwd, yolo, model, config_dir):
        yield RateLimitEvent(RateLimitInfo(reason="429 weekly limit"))

    monkeypatch.setattr(runner, "stream_via_cli_agent", fake_stream)
    monkeypatch.setattr(runner, "resolve_account_config_dir", lambda aid, backend: None)

    sh.run_streaming_response(
        session_id="sess-2",
        super_agent_id="psa-2",
        backend="claude",
        account_id=None,
    )

    kinds = [k for k, _ in deltas]
    assert "queued" in kinds
    assert "finish" not in kinds  # no content finalized
    # The turn is persisted for the scheduler to re-dispatch.
    pending = q.list_pending_chat_retries()
    assert any(r["session_id"] == "sess-2" for r in pending)
