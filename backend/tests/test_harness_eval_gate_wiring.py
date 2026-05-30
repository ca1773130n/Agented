"""Tests for the eval gate helper (_eval_gate) wired into run_evolution_round."""

from __future__ import annotations

from unittest.mock import patch

import app.services.harness_evolver as hv
from app.database import get_connection
from app.db import harness_evolution as evo
from app.models.harness_evolution import CheckResult, EvalVerdict


def _round():
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pg', 'P', 'active')")
        conn.commit()
    rid = evo.start_round(
        project_id="pg",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/x",
    )
    evo.mark_running(rid)
    return rid


class _FakePatch:
    entries = []


def test_eval_fail_short_circuits_and_blocks_apply(isolated_db, tmp_path):
    rid = _round()
    bad = EvalVerdict(
        passed=False,
        score=0.1,
        per_check=[CheckResult(name="static", passed=False, detail="x")],
    )
    with patch.object(hv, "evaluate_patch", return_value=bad, create=True):
        result = hv._eval_gate(rid, patch=_FakePatch(), inputs={"incidents": []}, scratch=tmp_path)
    assert result is not None and result.status == "eval_failed"
    assert evo.get_round(rid)["status"] == "eval_failed"


def test_eval_pass_returns_none_to_continue(isolated_db, tmp_path):
    rid = _round()
    good = EvalVerdict(
        passed=True,
        score=0.9,
        per_check=[CheckResult(name="static", passed=True)],
    )
    with patch.object(hv, "evaluate_patch", return_value=good, create=True):
        result = hv._eval_gate(rid, patch=_FakePatch(), inputs={"incidents": []}, scratch=tmp_path)
    assert result is None  # None => continue to dry-run/apply
    assert evo.get_round(rid)["status"] == "evaluating"  # stored verdict, not terminal


def test_gate_error_records_bypass_verdict_and_continues(isolated_db, tmp_path):
    rid = _round()

    def _boom(**kwargs):
        raise RuntimeError("eval infra down")

    with patch.object(hv, "evaluate_patch", _boom, create=True):
        result = hv._eval_gate(rid, patch=_FakePatch(), inputs={"incidents": []}, scratch=tmp_path)
    assert result is None  # fail-open: continue
    row = evo.get_round(rid)
    assert row["eval_verdict"] is not None
    assert row["eval_verdict"]["score"] == 0.0  # untrusted → autonomy won't auto-apply
    assert "bypass" in (row["eval_verdict"]["notes"] or "").lower()


def test_reaper_reaps_stale_evaluating_round(isolated_db):
    """A round stuck in 'evaluating' (crash during eval) must be reaped, not block forever."""
    rid = _round()
    evo.mark_evaluating(rid)
    # Backdate started_at far past the reaper threshold.
    with get_connection() as conn:
        conn.execute(
            "UPDATE harness_evolution_rounds SET started_at = '2000-01-01T00:00:00' WHERE id = ?",
            (rid,),
        )
        conn.commit()
    hv._check_rate_limit("pg", 1)  # triggers the reaper
    status = evo.get_round(rid)["status"]
    assert status in ("failed", "aborted")  # reaped, no longer in-flight
