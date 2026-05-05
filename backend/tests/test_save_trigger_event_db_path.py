"""v0.7.1: ExecutionService.save_trigger_event writes to DB instead of JSON."""

from app.services import trigger_event_service
from app.services.execution_service import ExecutionService


def test_save_trigger_event_writes_to_db(isolated_db):
    eid_str = ExecutionService.save_trigger_event(
        {"id": "trig-x", "name": "X", "trigger_source": "github"},
        {"foo": "bar"},
    )
    assert eid_str.isdigit()
    e = trigger_event_service.get(int(eid_str))
    assert e is not None
    assert e["trigger_id"] == "trig-x"
    # ensure_ascii=False output is compact-style; default json.dumps separators
    # produce '"foo": "bar"' — keep the assertion lenient so we don't pin
    # formatting choices.
    assert '"foo"' in e["payload"]
    assert '"bar"' in e["payload"]
    assert e["dispatch_status"] == "fired"
    assert e["matched"] == 1


def test_save_trigger_event_extracts_signature_header(isolated_db):
    eid_str = ExecutionService.save_trigger_event(
        {"id": "trig-y"},
        {"foo": "bar", "_signature_header": "sha256=zzz"},
    )
    e = trigger_event_service.get(int(eid_str))
    assert e["signature_header"] == "sha256=zzz"


def test_unmatched_dispatch_records_event(isolated_db, monkeypatch):
    """v0.7.1: dispatch_webhook_event records an unmatched event when no
    trigger or team matches the payload."""
    # Stub the DB lookups to return nothing — guarantees no match path.
    from app.services import trigger_dispatcher

    monkeypatch.setattr(trigger_dispatcher, "get_webhook_triggers", lambda: [])
    from app import database as _db

    monkeypatch.setattr(_db, "get_webhook_teams", lambda: [])

    fired = trigger_dispatcher.dispatch_webhook_event(
        {"event": "ping"},
        raw_payload=b'{"event":"ping"}',
        signature_header="sha=q",
    )
    assert fired is False

    # Look for the unmatched event row directly via service.
    from app.database import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT trigger_id, dispatch_status, matched, signature_header "
            "FROM trigger_events WHERE trigger_id IS NULL"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["dispatch_status"] == "unmatched"
    assert rows[0]["matched"] == 0
    assert rows[0]["signature_header"] == "sha=q"
