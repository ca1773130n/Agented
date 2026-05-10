"""v0.7.7: super-agent activity service tests."""

from datetime import datetime, timedelta, timezone

import pytest

from app.database import get_connection
from app.services import super_agent_activity_service as svc


def test_record_inserts_row(isolated_db):
    eid = svc.record(
        super_agent_id="sa-1",
        event_type="message_turn",
        payload={"role": "user", "content": "hi"},
        session_id="sess-1",
        cost_usd=0.01,
    )
    assert eid > 0
    with get_connection() as conn:
        row = conn.execute(
            "SELECT super_agent_id, session_id, event_type, payload, cost_usd, status "
            "FROM super_agent_activity WHERE id=?",
            (eid,),
        ).fetchone()
    assert row["super_agent_id"] == "sa-1"
    assert row["session_id"] == "sess-1"
    assert row["event_type"] == "message_turn"
    assert '"role": "user"' in row["payload"]
    assert row["cost_usd"] == 0.01
    assert row["status"] == "ok"


def test_record_accepts_string_payload(isolated_db):
    eid = svc.record(
        super_agent_id="sa-1",
        event_type="raw",
        payload='{"already":"json"}',
    )
    e = svc.get(eid)
    assert e["payload"] == '{"already":"json"}'


def test_list_returns_recent_first(isolated_db):
    for i in range(3):
        svc.record(
            super_agent_id="sa-1",
            event_type="message_turn",
            payload={"i": i},
        )
    rows = svc.list_for_super_agent("sa-1", limit=10)
    assert len(rows) == 3
    assert rows[0]["id"] > rows[1]["id"] > rows[2]["id"]


def test_list_respects_limit(isolated_db):
    for _ in range(5):
        svc.record(super_agent_id="sa-1", event_type="t", payload={})
    assert len(svc.list_for_super_agent("sa-1", limit=2)) == 2


def test_list_filters_by_type(isolated_db):
    svc.record(super_agent_id="sa-1", event_type="message_turn", payload={})
    svc.record(super_agent_id="sa-1", event_type="tool_call", payload={})
    svc.record(super_agent_id="sa-1", event_type="git_action", payload={})
    rows = svc.list_for_super_agent("sa-1", types=["message_turn", "tool_call"])
    assert len(rows) == 2
    assert {r["event_type"] for r in rows} == {"message_turn", "tool_call"}


def test_list_filters_by_since(isolated_db):
    svc.record(super_agent_id="sa-1", event_type="t", payload={})
    cutoff = datetime.now(timezone.utc).isoformat()
    # Backdate the row to before cutoff
    with get_connection() as conn:
        conn.execute(
            "UPDATE super_agent_activity SET recorded_at = ?",
            ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),),
        )
        conn.commit()
    assert svc.list_for_super_agent("sa-1", since=cutoff) == []


def test_list_for_session(isolated_db):
    svc.record(super_agent_id="sa-1", session_id="sess-A", event_type="t", payload={})
    svc.record(super_agent_id="sa-1", session_id="sess-B", event_type="t", payload={})
    rows = svc.list_for_session("sess-A")
    assert len(rows) == 1
    assert rows[0]["session_id"] == "sess-A"


def test_get_returns_full_row(isolated_db):
    eid = svc.record(
        super_agent_id="sa-1",
        event_type="model_invoke",
        payload={"model": "opus"},
        cost_tokens_in=100,
        cost_tokens_out=50,
        cost_usd=0.02,
        duration_ms=1234,
    )
    e = svc.get(eid)
    assert e["cost_tokens_in"] == 100
    assert e["cost_tokens_out"] == 50
    assert e["cost_usd"] == 0.02
    assert e["duration_ms"] == 1234


def test_get_returns_none_for_unknown(isolated_db):
    assert svc.get(99999) is None


def test_rollup_no_events_idle(isolated_db):
    r = svc.rollup("sa-empty")
    assert r.event_count == 0
    assert r.error_count == 0
    assert r.last_active_at is None
    assert r.status_pill == "idle"
    assert r.cost_per_event_avg is None
    assert r.error_rate is None


def test_rollup_recent_active(isolated_db):
    svc.record(super_agent_id="sa-1", event_type="t", payload={}, cost_usd=0.05)
    r = svc.rollup("sa-1")
    assert r.event_count == 1
    assert r.error_count == 0
    assert r.total_cost_usd == 0.05
    assert r.status_pill == "active"
    assert r.cost_per_event_avg == 0.05
    assert r.error_rate == 0.0


def test_rollup_high_error_rate_degraded(isolated_db):
    # 10 events, 2 errors → 20% error rate → degraded.
    # Backdate to outside the 5-minute "active" window so the classifier
    # falls through to the error-rate branch.
    for i in range(10):
        svc.record(
            super_agent_id="sa-1",
            event_type="t",
            payload={"i": i},
            status="error" if i < 2 else "ok",
        )
    with get_connection() as conn:
        conn.execute(
            "UPDATE super_agent_activity SET recorded_at = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),),
        )
        conn.commit()
    r = svc.rollup("sa-1")
    assert r.event_count == 10
    assert r.error_count == 2
    assert r.error_rate == pytest.approx(0.2)
    assert r.status_pill == "errored"


def test_rollup_last_event_error_marks_errored(isolated_db):
    svc.record(super_agent_id="sa-1", event_type="t", payload={}, status="ok")
    svc.record(
        super_agent_id="sa-1",
        event_type="t",
        payload={},
        status="error",
        error_message="boom",
    )
    # Backdate past the active window; status_pill should still be 'errored'
    # because the most recent event was an error.
    with get_connection() as conn:
        conn.execute(
            "UPDATE super_agent_activity SET recorded_at = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),),
        )
        conn.commit()
    r = svc.rollup("sa-1")
    assert r.status_pill == "errored"


def test_rollup_idle_when_old_events(isolated_db):
    svc.record(super_agent_id="sa-1", event_type="t", payload={})
    with get_connection() as conn:
        conn.execute(
            "UPDATE super_agent_activity SET recorded_at = ?",
            ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),),
        )
        conn.commit()
    r = svc.rollup("sa-1", window_days=7)
    assert r.status_pill == "idle"


def test_rollup_window_validation(isolated_db):
    with pytest.raises(ValueError):
        svc.rollup("sa-1", window_days=0)
    with pytest.raises(ValueError):
        svc.rollup("sa-1", window_days=91)


def test_purge_older_than(isolated_db):
    old_eid = svc.record(super_agent_id="sa-1", event_type="t", payload={})
    with get_connection() as conn:
        conn.execute(
            "UPDATE super_agent_activity SET recorded_at = ? WHERE id = ?",
            (
                (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
                old_eid,
            ),
        )
        conn.commit()
    new_eid = svc.record(super_agent_id="sa-1", event_type="t", payload={})
    deleted = svc.purge_older_than(days=30)
    assert deleted == 1
    assert svc.get(old_eid) is None
    assert svc.get(new_eid) is not None
