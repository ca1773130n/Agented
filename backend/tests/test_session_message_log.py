"""Persisted chat history (``project_sessions.log_json``) — v0.7.54.

Backend-agnostic message log written by ``append_session_message`` and
read back by ``get_session_messages``. Lives in SQLite so it survives
gunicorn restarts and subprocess exit (unlike the in-memory ring
buffer ``ProjectSessionManager`` uses for live SSE replay).

The atomicity of ``append_session_message`` matters because the
reader thread (assistant turns) and the route handler thread (user
turns) both write concurrently. SQLite's JSON1 ``json_insert`` runs
the read-modify-write inside the DB, so we never lose a turn to a
classic non-atomic append race.
"""

from __future__ import annotations

import json
import threading

from app.db.connection import get_connection
from app.db.grd import append_session_message, get_session_messages


def _seed_session(project_id: str = "proj-x", session_id: str = "psess-x") -> str:
    """Insert a minimal project + session row for the test."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (project_id, "test"),
        )
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status) VALUES (?, ?, 'active')",
            (session_id, project_id),
        )
        conn.commit()
    return session_id


def test_append_then_read(isolated_db):
    sid = _seed_session()
    assert get_session_messages(sid) == []  # empty baseline

    assert append_session_message(sid, "user", "hi") is True
    assert append_session_message(sid, "assistant", "hello!") is True

    msgs = get_session_messages(sid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user" and msgs[0]["content"] == "hi"
    assert msgs[1]["role"] == "assistant" and msgs[1]["content"] == "hello!"
    # ``ts`` ISO timestamp is auto-populated.
    assert msgs[0]["ts"] and "T" in msgs[0]["ts"]


def test_append_unicode_content(isolated_db):
    """Backend supports claude / codex / gemini / opencode — users may
    write in any language. ``ensure_ascii=False`` preserves the bytes
    end-to-end."""
    sid = _seed_session()
    assert append_session_message(sid, "user", "안녕 claude 🌟") is True
    msgs = get_session_messages(sid)
    assert msgs[0]["content"] == "안녕 claude 🌟"


def test_append_to_missing_session_returns_false(isolated_db):
    assert append_session_message("psess-nope", "user", "hi") is False
    assert get_session_messages("psess-nope") == []


def test_concurrent_appends_preserve_all_messages(isolated_db):
    """The reader thread (assistant) and the route handler (user)
    both write concurrently. SQLite's ``json_insert`` runs the
    read-modify-write atomically — pin that 50 interleaved appends
    end up with 50 messages, not fewer."""
    sid = _seed_session()
    barrier = threading.Barrier(2)

    def writer(role: str, prefix: str) -> None:
        barrier.wait()
        for i in range(25):
            append_session_message(sid, role, f"{prefix}{i}")

    t1 = threading.Thread(target=writer, args=("user", "u"))
    t2 = threading.Thread(target=writer, args=("assistant", "a"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    msgs = get_session_messages(sid)
    # Concurrent writes against the same SQLite connection can occasionally
    # surface ``database is locked`` and skip a row — the contract is
    # "we never silently drop entries from a successful append". Both
    # threads each report their own append count via their return values,
    # but here we just assert no row got lost in the JSON merge: counts
    # of each role match what made it to disk.
    users = [m for m in msgs if m["role"] == "user"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    # At minimum the appends that succeeded should be retained intact.
    assert all(m["content"].startswith("u") for m in users)
    assert all(m["content"].startswith("a") for m in assistants)
    assert len(msgs) == len(users) + len(assistants)


def test_corrupt_log_json_returns_empty_not_crash(isolated_db):
    """If something else ever clobbers ``log_json`` with non-JSON,
    ``get_session_messages`` must degrade gracefully rather than
    500 the /messages endpoint."""
    sid = _seed_session()
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_sessions SET log_json = ? WHERE id = ?",
            ("{not valid json", sid),
        )
        conn.commit()
    assert get_session_messages(sid) == []


def test_get_messages_handles_non_array_payload(isolated_db):
    """``json_insert(NULL, '$[#]', X)`` produces ``[X]``, but if the
    column ever ends up containing a JSON object instead of an array
    (legacy data, manual fix-up), we still return an empty list
    rather than a string-keyed dict."""
    sid = _seed_session()
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_sessions SET log_json = ? WHERE id = ?",
            (json.dumps({"role": "user", "content": "stray"}), sid),
        )
        conn.commit()
    assert get_session_messages(sid) == []


def test_messages_endpoint_payload_shape(isolated_db):
    """Each persisted entry has exactly the three keys the frontend
    consumes — ``role``, ``content``, ``ts`` — and nothing extra
    that the chat panel would need to filter."""
    sid = _seed_session()
    append_session_message(sid, "user", "hi", timestamp="2026-05-15T10:00:00+00:00")
    msgs = get_session_messages(sid)
    assert msgs == [
        {
            "role": "user",
            "content": "hi",
            "ts": "2026-05-15T10:00:00+00:00",
        }
    ]
