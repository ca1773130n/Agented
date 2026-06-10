# backend/tests/test_verification_service.py
"""VerificationService write facade (Harness-1 Phase 2, P5)."""

from app.db import verification_records as vr
from app.services.verification_service import VerificationService


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


def test_record_writes_a_verification_row():
    _make_execution()
    rid = VerificationService.record("exec-1", "no secrets", status="passed", evidence_ref="scan.json")
    assert rid > 0
    rows = vr.list_verifications("exec-1")
    assert rows[0]["claim"] == "no secrets"
    assert rows[0]["status"] == "passed"
