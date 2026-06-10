"""The P5 advisory gate blocks the PR side-effect only on a failed claim."""

from app.db import verification_records as vr
from app.services.execution_service import _verification_pr_gate


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


def test_gate_allows_when_no_records():
    _make_execution()
    assert _verification_pr_gate("exec-1") is True


def test_gate_allows_when_only_passed():
    _make_execution()
    vr.record_verification("exec-1", "lint", status="passed")
    assert _verification_pr_gate("exec-1") is True


def test_gate_blocks_when_a_claim_failed():
    _make_execution()
    vr.record_verification("exec-1", "no high-sev CVEs", status="failed")
    assert _verification_pr_gate("exec-1") is False


def test_call_site_runs_side_effect_when_gate_allows():
    """_maybe_auto_resolve_and_pr (used by run_trigger at :672) invokes the
    side-effect when no claim failed."""
    from unittest.mock import patch

    from app.services.execution_service import ExecutionService

    _make_execution()
    with patch("app.services.execution_service.auto_resolve_and_pr") as m:
        ExecutionService._maybe_auto_resolve_and_pr("exec-1", {"id": "t"}, {"r": "x"}, "out")
    m.assert_called_once_with({"id": "t"}, {"r": "x"}, "out")


def test_call_site_skips_side_effect_when_a_claim_failed():
    """The wiring is real: a failed verification record skips the PR side-effect."""
    from unittest.mock import patch

    from app.services.execution_service import ExecutionService

    _make_execution()
    vr.record_verification("exec-1", "no high-sev CVEs", status="failed")
    with patch("app.services.execution_service.auto_resolve_and_pr") as m:
        ExecutionService._maybe_auto_resolve_and_pr("exec-1", {"id": "t"}, {"r": "x"}, "out")
    m.assert_not_called()
