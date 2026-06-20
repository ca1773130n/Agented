"""v0.7.1: trigger event service tests."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.database import get_connection
from app.services import trigger_event_service as svc


def test_record_inserts_row(isolated_db):
    eid = svc.record(
        trigger_id="trig-1",
        payload='{"foo": "bar"}',
        signature_header="sha256=abc",
        dispatch_status="fired",
        matched=True,
    )
    assert eid > 0
    with get_connection() as conn:
        row = conn.execute(
            "SELECT trigger_id, payload, dispatch_status, matched FROM trigger_events WHERE id=?",
            (eid,),
        ).fetchone()
    assert row["trigger_id"] == "trig-1"
    assert row["payload"] == '{"foo": "bar"}'
    assert row["dispatch_status"] == "fired"
    assert row["matched"] == 1


def test_record_unmatched_allows_null_trigger_id(isolated_db):
    eid = svc.record(
        trigger_id=None,
        payload="{}",
        signature_header=None,
        dispatch_status="unmatched",
        matched=False,
    )
    e = svc.get(eid)
    assert e["trigger_id"] is None
    assert e["matched"] == 0


def test_list_for_trigger_returns_recent_first(isolated_db):
    for i in range(3):
        svc.record(
            trigger_id="t1",
            payload=f'{{"i":{i}}}',
            signature_header=None,
            dispatch_status="fired",
            matched=True,
        )
    rows = svc.list_for_trigger("t1", limit=10)
    assert len(rows) == 3
    # Most recent first
    assert rows[0]["id"] > rows[1]["id"] > rows[2]["id"]


def test_list_for_trigger_respects_limit(isolated_db):
    for _ in range(5):
        svc.record(
            trigger_id="t1",
            payload="{}",
            signature_header=None,
            dispatch_status="fired",
            matched=True,
        )
    assert len(svc.list_for_trigger("t1", limit=2)) == 2


def test_get_returns_full_row(isolated_db):
    eid = svc.record(
        trigger_id="t1",
        payload='{"k":"v"}',
        signature_header="sha=1",
        dispatch_status="fired",
        matched=True,
    )
    e = svc.get(eid)
    assert e["payload"] == '{"k":"v"}'
    assert e["signature_header"] == "sha=1"


def test_get_returns_none_for_unknown(isolated_db):
    assert svc.get(99999) is None


def test_replay_calls_dispatcher_with_stored_payload(isolated_db, monkeypatch):
    eid = svc.record(
        trigger_id="t1",
        payload='{"event":"x"}',
        signature_header="sha=z",
        dispatch_status="fired",
        matched=True,
    )
    fake = MagicMock(return_value=True)
    monkeypatch.setattr(
        "app.services.execution_service.ExecutionService.dispatch_webhook_event",
        fake,
    )
    result = svc.replay(eid)
    assert result is True
    fake.assert_called_once()
    kwargs = fake.call_args.kwargs
    args = fake.call_args.args
    # Either positional payload dict or keyword — accept both
    payload = args[0] if args else kwargs.get("payload")
    assert payload == {"event": "x"}


def test_replay_unknown_event_raises(isolated_db):
    with pytest.raises(LookupError):
        svc.replay(99999)


def test_replay_skips_signature_validation(isolated_db, monkeypatch):
    """Admin replay must bypass HMAC validation — original raw bytes are gone."""
    eid = svc.record(
        trigger_id="t1",
        payload='{"event":"x"}',
        # Non-matching signature: any sig over the stored payload would not
        # match the original signed raw bytes anyway. Replay must not let
        # webhook_secret triggers reject this on signature mismatch.
        signature_header="sha256=does-not-match",
        dispatch_status="fired",
        matched=True,
    )
    captured: dict = {}

    def fake_dispatch(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return True

    monkeypatch.setattr(
        "app.services.execution_service.ExecutionService.dispatch_webhook_event",
        fake_dispatch,
    )
    result = svc.replay(eid)
    assert result is True
    assert captured["kwargs"].get("skip_signature_validation") is True


def test_purge_older_than_drops_old_rows(isolated_db):
    old_eid = svc.record(
        trigger_id="t1",
        payload="{}",
        signature_header=None,
        dispatch_status="fired",
        matched=True,
    )
    # Manually backdate
    with get_connection() as conn:
        conn.execute(
            "UPDATE trigger_events SET received_at=? WHERE id=?",
            (
                (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
                old_eid,
            ),
        )
        conn.commit()
    new_eid = svc.record(
        trigger_id="t1",
        payload="{}",
        signature_header=None,
        dispatch_status="fired",
        matched=True,
    )
    deleted = svc.purge_older_than(days=30)
    assert deleted == 1
    assert svc.get(old_eid) is None
    assert svc.get(new_eid) is not None
