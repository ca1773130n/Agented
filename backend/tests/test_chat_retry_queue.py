"""Tests for the chat retry queue (rate-limit rotation Phase 2): DB helpers
and the ChatRetryService scheduler tick."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db import chat_retry_queue as q
from app.services.chat_retry_service import MAX_ATTEMPTS, ChatRetryService


def _enqueue(session_id="sess-1", backend="claude", use_cli_agent=True):
    q.enqueue_chat_retry(
        session_id=session_id,
        super_agent_id="psa-1",
        backend=backend,
        account_id=None,
        model=None,
        cwd=None,
        chat_mode="management",
        instance_id=None,
        use_cli_agent=use_cli_agent,
        reason="weekly limit",
    )


def test_table_exists_after_init(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_retry_queue'"
        ).fetchone()
    assert row is not None


def test_enqueue_then_list_and_delete(isolated_db):
    _enqueue(use_cli_agent=True)
    pending = q.list_pending_chat_retries()
    assert len(pending) == 1
    assert pending[0]["session_id"] == "sess-1"
    assert pending[0]["use_cli_agent"] is True
    assert pending[0]["attempts"] == 0
    assert q.count_pending_chat_retries() == 1

    q.delete_chat_retry("sess-1")
    assert q.count_pending_chat_retries() == 0


def test_enqueue_is_idempotent_per_session_and_bumps_attempts(isolated_db):
    _enqueue()
    _enqueue()  # same session_id → upsert
    pending = q.list_pending_chat_retries()
    assert len(pending) == 1
    assert pending[0]["attempts"] == 1  # bumped on conflict


def test_use_cli_agent_tristate_roundtrip(isolated_db):
    _enqueue(session_id="a", use_cli_agent=None)
    _enqueue(session_id="b", use_cli_agent=False)
    by_id = {r["session_id"]: r for r in q.list_pending_chat_retries()}
    assert by_id["a"]["use_cli_agent"] is None
    assert by_id["b"]["use_cli_agent"] is False


# --- scheduler tick -------------------------------------------------------


def _seed_claude_account(rate_limited: bool):
    from app.db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute("SELECT id FROM ai_backends WHERE type='claude' LIMIT 1").fetchone()
        backend_id = row[0] if row else "rot-claude"
        if not row:
            conn.execute(
                "INSERT INTO ai_backends (id, type, name, is_installed) VALUES (?,?,?,1)",
                (backend_id, "claude", "Claude"),
            )
        conn.execute("DELETE FROM backend_accounts WHERE backend_id=?", (backend_id,))
        rl = (datetime.now() + timedelta(hours=3)).isoformat() if rate_limited else None
        conn.execute(
            "INSERT INTO backend_accounts (backend_id, account_name, config_path, is_default, rate_limited_until) "
            "VALUES (?,?,?,1,?)",
            (backend_id, "Personal1", "~/.claude-personal1", rl),
        )
        conn.commit()


def test_process_pending_leaves_queued_when_no_eligible_account(isolated_db, monkeypatch):
    _seed_claude_account(rate_limited=True)  # only account is still limited
    _enqueue()

    dispatched_calls = []
    monkeypatch.setattr(
        "app.services.streaming_helper.run_streaming_response",
        lambda **kw: dispatched_calls.append(kw),
    )

    n = ChatRetryService.process_pending()
    assert n == 0
    assert dispatched_calls == []
    assert q.count_pending_chat_retries() == 1  # still queued


def test_process_pending_redispatches_when_account_frees(isolated_db, monkeypatch):
    _seed_claude_account(rate_limited=False)  # an eligible account now exists
    _enqueue()

    dispatched_calls = []
    monkeypatch.setattr(
        "app.services.streaming_helper.run_streaming_response",
        lambda **kw: dispatched_calls.append(kw),
    )
    pushed = []
    monkeypatch.setattr(
        "app.services.chat_state_service.ChatStateService.push_delta",
        lambda sid, kind, payload: pushed.append((sid, kind)),
    )

    n = ChatRetryService.process_pending()
    assert n == 1
    assert len(dispatched_calls) == 1
    assert dispatched_calls[0]["session_id"] == "sess-1"
    assert dispatched_calls[0]["super_agent_id"] == "psa-1"
    # Row removed before dispatch so the next tick can't double-fire.
    assert q.count_pending_chat_retries() == 0
    assert ("sess-1", "retry_dispatch") in pushed


def test_process_pending_gives_up_after_max_attempts(isolated_db, monkeypatch):
    _seed_claude_account(rate_limited=False)
    _enqueue()
    # Force attempts to the cap.
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_retry_queue SET attempts=? WHERE session_id='sess-1'", (MAX_ATTEMPTS,)
        )
        conn.commit()

    dispatched_calls = []
    monkeypatch.setattr(
        "app.services.streaming_helper.run_streaming_response",
        lambda **kw: dispatched_calls.append(kw),
    )
    errors = []
    monkeypatch.setattr(
        "app.services.chat_state_service.ChatStateService.push_delta",
        lambda sid, kind, payload: errors.append((kind, payload.get("kind"))),
    )
    monkeypatch.setattr(
        "app.services.chat_state_service.ChatStateService.push_status",
        lambda *a, **k: None,
    )

    n = ChatRetryService.process_pending()
    assert n == 0
    assert dispatched_calls == []  # did not dispatch
    assert q.count_pending_chat_retries() == 0  # removed
    assert ("error", "rate_limited_giveup") in errors
