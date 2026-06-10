# backend/tests/test_verification_records_repo.py
"""Repository for P5 verification records."""

from app.db import verification_records as vr
from app.db.connection import get_connection


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_record_verification_pending_has_no_checked_at():
    _make_execution()
    rid = vr.record_verification("exec-1", "tests pass")
    assert rid > 0
    rows = vr.list_verifications("exec-1")
    assert rows[0]["status"] == "pending"
    assert rows[0]["checked_at"] is None


def test_record_verification_terminal_sets_checked_at():
    _make_execution()
    vr.record_verification("exec-1", "no secrets", status="passed", evidence_ref="scan.json")
    row = vr.list_verifications("exec-1")[0]
    assert row["status"] == "passed"
    assert row["evidence_ref"] == "scan.json"
    assert row["checked_at"] is not None


def test_has_failed_only_true_when_a_failed_record_exists():
    _make_execution()
    assert vr.has_failed("exec-1") is False
    vr.record_verification("exec-1", "lint clean", status="passed")
    assert vr.has_failed("exec-1") is False
    vr.record_verification("exec-1", "no high-sev CVEs", status="failed")
    assert vr.has_failed("exec-1") is True


def test_list_empty_for_unknown_execution():
    assert vr.list_verifications("nope") == []


def test_fk_cascade_delete_removes_records():
    _make_execution()
    vr.record_verification("exec-1", "x", status="failed")
    with get_connection() as conn:
        conn.execute("DELETE FROM execution_logs WHERE execution_id = ?", ("exec-1",))
        conn.commit()
    assert vr.list_verifications("exec-1") == []
    assert vr.has_failed("exec-1") is False
