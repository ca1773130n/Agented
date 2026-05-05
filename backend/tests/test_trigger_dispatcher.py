"""v0.7.1: trigger_dispatcher.dispatch_webhook_event regression tests.

Focused on the matched-vs-triggered distinction: a trigger that matches a
payload but fails to dispatch (queue full, session limit) must not also be
recorded as an unmatched event.
"""

from __future__ import annotations

from app import database as _db
from app.database import get_connection
from app.services import trigger_dispatcher


def _make_trigger(**overrides):
    t = {
        "id": "trg-disp01",
        "name": "Dispatcher Test",
        "trigger_source": "webhook",
        "backend_type": "claude",
        "prompt_template": "Analyze {message}",
        "enabled": 1,
        "text_field_path": "body",
        "detection_keyword": "",
    }
    t.update(overrides)
    return t


def test_match_with_failed_dispatch_does_not_record_unmatched(isolated_db, monkeypatch):
    """Queue-full on a matched trigger must not record a false 'unmatched' row.

    Before the fix, the unmatched-event branch was keyed off ``triggered``,
    so a match that failed to dispatch (raising QueueFullError) was both
    matched (saved as 'fired' by save_trigger_event_fn) AND falsely recorded
    as 'unmatched' — two rows for one payload.
    """
    trigger = _make_trigger()
    monkeypatch.setattr(trigger_dispatcher, "get_webhook_triggers", lambda: [trigger])
    monkeypatch.setattr(_db, "get_webhook_teams", lambda: [])
    # Bypass dedup so the match path proceeds to enqueue.
    monkeypatch.setattr(
        "app.services.trigger_dispatcher.check_and_insert_dedup_key",
        lambda **kw: True,
    )

    from app.services import execution_queue_service

    def boom(**kwargs):
        raise execution_queue_service.QueueFullError("queue full")

    monkeypatch.setattr(execution_queue_service.ExecutionQueueService, "enqueue", boom)

    # Use a no-op save_trigger_event_fn so we can isolate the unmatched path.
    saves: list = []

    def fake_save(trigger_dict, event):
        saves.append((trigger_dict, event))
        return "1"

    fired = trigger_dispatcher.dispatch_webhook_event(
        {"body": "hello world"},
        save_trigger_event_fn=fake_save,
    )
    # Dispatch failed → triggered is False
    assert fired is False
    # But save_trigger_event_fn was called for the match
    assert len(saves) == 1

    # Critical assertion: no 'unmatched' row was recorded.
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, trigger_id, dispatch_status, matched FROM trigger_events "
            "WHERE dispatch_status = 'unmatched'"
        ).fetchall()
    assert rows == [], f"Expected no unmatched row, got {[dict(r) for r in rows]}"


def test_no_match_still_records_unmatched(isolated_db, monkeypatch):
    """Sanity check: when nothing matches, we still record the unmatched event."""
    monkeypatch.setattr(trigger_dispatcher, "get_webhook_triggers", lambda: [])
    monkeypatch.setattr(_db, "get_webhook_teams", lambda: [])

    fired = trigger_dispatcher.dispatch_webhook_event(
        {"body": "no match here"},
        save_trigger_event_fn=lambda t, e: "1",
    )
    assert fired is False

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT trigger_id, dispatch_status, matched FROM trigger_events "
            "WHERE dispatch_status = 'unmatched'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["trigger_id"] is None
    assert rows[0]["matched"] == 0
