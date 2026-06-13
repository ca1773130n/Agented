"""Regression: the leader-chat SSE registers a REAL session before subscribing.

Bug: the team-leader chat opens
``/admin/super-agents/{sa}/sessions/{sid}/chat/stream`` when its panel MOUNTS
(``resolveAndConnect`` → ``openSession`` → ``connectStream``) — before any
message turn has registered the session in ChatStateService. ``subscribe()``
then fell through to ``yield "Session not found"`` and the EventSource
reconnect-looped (the operator saw repeated ⚠ "Session not found").

Fix: ``_ensure_chat_session_registered`` pre-registers a real session
(idempotent) so an idle subscriber waits for deltas; an unknown id is left
unregistered so subscribe still reports not-found.
"""

from __future__ import annotations

import json

from app.services.chat_state_service import ChatStateService
from app_litestar.routes.streams import _ensure_chat_session_registered


def test_registers_real_session(isolated_db, monkeypatch):
    sid = "sess-leader-real"
    ChatStateService.remove_session(sid)
    monkeypatch.setattr(
        "app.db.super_agents.get_super_agent_session",
        lambda s: {"id": s, "session_type": "leader"},
    )
    assert _ensure_chat_session_registered(sid) is True
    assert sid in ChatStateService._sessions
    ChatStateService.remove_session(sid)


def test_unknown_session_left_unregistered(isolated_db, monkeypatch):
    sid = "sess-leader-unknown"
    ChatStateService.remove_session(sid)
    monkeypatch.setattr("app.db.super_agents.get_super_agent_session", lambda s: None)
    assert _ensure_chat_session_registered(sid) is False
    assert sid not in ChatStateService._sessions


def test_unregistered_session_still_yields_not_found(isolated_db):
    """The 'Session not found' path is preserved for genuinely-absent sessions."""
    sid = "sess-absent"
    ChatStateService.remove_session(sid)
    gen = ChatStateService.subscribe(sid, 0)
    first = next(gen)
    assert "Session not found" in first


def test_registered_session_replays_instead_of_erroring(isolated_db, monkeypatch):
    """After registration, a reconnecting subscriber (last_seq>0) replays the
    missed delta — NOT 'Session not found'. (Uses last_seq>0 so the replay
    path runs and the generator doesn't block on the heartbeat.)"""
    sid = "sess-leader-replay"
    ChatStateService.remove_session(sid)
    monkeypatch.setattr(
        "app.db.super_agents.get_super_agent_session",
        lambda s: {"id": s, "session_type": "leader"},
    )
    _ensure_chat_session_registered(sid)
    ChatStateService.push_delta(sid, "planning", {"status": "started"})  # seq 1
    ChatStateService.push_delta(sid, "retrieval", {"chunks": 3})  # seq 2

    gen = ChatStateService.subscribe(sid, 1)  # saw seq 1 → replays seq 2
    first = next(gen)
    assert "Session not found" not in first
    assert "state_delta" in first
    payload = json.loads(first.split("data: ", 1)[1])
    assert payload["seq"] == 2
    assert payload["type"] == "retrieval"
    ChatStateService.remove_session(sid)  # poison-pill any wait


def test_idempotent_does_not_reset_event_log(isolated_db, monkeypatch):
    """Re-registering on reconnect must not wipe a session's events."""
    sid = "sess-leader-reconnect"
    ChatStateService.remove_session(sid)
    monkeypatch.setattr(
        "app.db.super_agents.get_super_agent_session",
        lambda s: {"id": s, "session_type": "leader"},
    )
    _ensure_chat_session_registered(sid)
    ChatStateService.push_delta(sid, "marker", {"keep": True})
    seq = ChatStateService._sessions[sid]["seq"]

    _ensure_chat_session_registered(sid)  # reconnect

    assert ChatStateService._sessions[sid]["seq"] == seq
    assert any(e.get("keep") for e in ChatStateService._sessions[sid]["event_log"])
    ChatStateService.remove_session(sid)
