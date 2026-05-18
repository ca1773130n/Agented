"""Tests for the GoalLoopRunner Ouroboros adaptation
(v0.7.86 introduced as opt-in; v0.7.87 flipped the default to on).

Covers:
  * Migration v128 created the schema additions.
  * Hypothesis/predicted extraction from agent turn text.
  * Prompt helpers: default-on Ouroboros shape vs explicit opt-out
    via ``ouroboros=False``.
  * GoalJudgeService ouroboros mode (mocked HTTP) returning a
    4-state verdict.
  * Dead-end registry idempotency.
  * Convergence-window verdict tracking.
"""

from __future__ import annotations

from unittest.mock import patch

from app.db.connection import get_connection
from app.db.goal_loop import (
    add_goal_loop_dead_end,
    list_goal_loop_dead_ends,
    recent_iteration_verdicts,
    record_iteration_complete,
    record_iteration_start,
)
from app.services.goal_judge_service import (
    GoalJudgeService,
    JudgeVerdict,
    _parse_ouroboros_judge_json,
)
from app.services.goal_loop_runner import (
    _approach_hash,
    _continue_prompt,
    _dead_ends_context,
    _extract_hypothesis,
    _initial_prompt,
)


# ---------------------------------------------------------------------
# Migration v128
# ---------------------------------------------------------------------


def test_migration_128_columns_and_table(isolated_db):
    del isolated_db
    with get_connection() as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(goal_loop_iterations)").fetchall()
        }
        for col in ("hypothesis", "predicted_outcome", "ouroboros_verdict"):
            assert col in cols, f"migration 128 must add goal_loop_iterations.{col}"
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "goal_loop_dead_ends" in tables


# ---------------------------------------------------------------------
# Hypothesis extraction
# ---------------------------------------------------------------------


def test_extract_hypothesis_handles_markdown_bold():
    text = (
        "**Hypothesis:** Adding a cache will reduce p95 latency\n"
        "**Predicted outcome:** p95 drops below 100ms in the next bench\n"
        "\n"
        "Now implementing..."
    )
    hyp, pred = _extract_hypothesis(text)
    assert hyp == "Adding a cache will reduce p95 latency"
    assert pred == "p95 drops below 100ms in the next bench"


def test_extract_hypothesis_plaintext_form():
    text = "Hypothesis: rewrite as recursion\nPredicted outcome: no stack overflow on N=10000"
    hyp, pred = _extract_hypothesis(text)
    assert hyp == "rewrite as recursion"
    assert pred == "no stack overflow on N=10000"


def test_extract_hypothesis_returns_none_when_missing():
    hyp, pred = _extract_hypothesis("Just plain agent output, no markers.")
    assert hyp is None
    assert pred is None


# ---------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------


def test_initial_prompt_default_asks_for_hypothesis():
    """v0.7.87 — ``ouroboros`` defaults to ``True``; calling the
    helper with no kwargs still asks for the markers.
    """
    out = _initial_prompt("ship feature")
    assert "**Hypothesis:**" in out
    assert "**Predicted outcome:**" in out


def test_initial_prompt_opt_out_skips_hypothesis():
    """Operators can still disable Ouroboros explicitly."""
    out = _initial_prompt("ship feature", ouroboros=False)
    assert "Hypothesis" not in out
    assert "Make progress this turn" in out


def test_continue_prompt_default_asks_for_hypothesis():
    out = _continue_prompt("ship feature", "missing tests")
    assert "**Hypothesis:**" in out
    assert "**Predicted outcome:**" in out


def test_continue_prompt_opt_out_uses_legacy_tail():
    out = _continue_prompt("ship feature", "missing tests", ouroboros=False)
    assert "Hypothesis" not in out
    assert "Address the gap and continue." in out


def test_continue_prompt_injects_dead_ends_block():
    block = "Previously falsified approaches (do NOT retry these):\n- A — fail\n- B — fail"
    out = _continue_prompt("ship feature", "missing tests", dead_ends_block=block)
    assert "Previously falsified" in out
    assert "**Hypothesis:**" in out


# ---------------------------------------------------------------------
# Dead-end registry
# ---------------------------------------------------------------------


def test_add_dead_end_dedupes_on_approach_hash(isolated_db):
    del isolated_db
    sid = "psess-test1234"
    h = _approach_hash("Use caching")
    rid1 = add_goal_loop_dead_end(
        session_id=sid,
        iteration=1,
        approach="Use caching",
        reason="cache stampede",
        approach_hash=h,
    )
    rid2 = add_goal_loop_dead_end(
        session_id=sid,
        iteration=2,
        approach="Use caching",
        reason="still stampeding",
        approach_hash=h,
    )
    assert rid1 is not None
    assert rid2 is None  # duplicate hash → silently dropped
    assert len(list_goal_loop_dead_ends(sid)) == 1


def test_dead_ends_context_renders_bullets(isolated_db):
    del isolated_db
    sid = "psess-test5678"
    add_goal_loop_dead_end(
        session_id=sid,
        iteration=1,
        approach="Approach A",
        reason="reason A",
        approach_hash="hashA",
    )
    add_goal_loop_dead_end(
        session_id=sid,
        iteration=2,
        approach="Approach B",
        reason="reason B",
        approach_hash="hashB",
    )
    block = _dead_ends_context(sid)
    assert "Previously falsified" in block
    assert "Approach A" in block
    assert "Approach B" in block


def test_dead_ends_context_empty_returns_blank_string(isolated_db):
    del isolated_db
    assert _dead_ends_context("psess-nothinghere") == ""


# ---------------------------------------------------------------------
# Convergence detection (recent_iteration_verdicts)
# ---------------------------------------------------------------------


def test_recent_iteration_verdicts_returns_window_oldest_first(isolated_db):
    del isolated_db
    sid = "psess-convergence"
    # Seed 5 iterations with mixed verdicts.
    for i, verdict in enumerate(
        ["confirmed", "partial", "falsified", "falsified", "falsified"], start=1
    ):
        row_id = record_iteration_start(sid, i)
        record_iteration_complete(
            row_id,
            verdict="met" if verdict == "confirmed" else "not_met",
            judge_source="llm",
            judge_reason="test",
            ouroboros_verdict=verdict,
        )
    recent = recent_iteration_verdicts(sid, limit=3)
    assert recent == ["falsified", "falsified", "falsified"]


def test_recent_iteration_verdicts_ignores_legacy_rows(isolated_db):
    del isolated_db
    sid = "psess-mixed"
    # One iteration without ouroboros_verdict (legacy shape).
    row_id = record_iteration_start(sid, 1)
    record_iteration_complete(
        row_id, verdict="not_met", judge_source="llm", judge_reason="legacy"
    )
    # Two iterations with ouroboros_verdict.
    for i, verdict in enumerate(["falsified", "partial"], start=2):
        row_id = record_iteration_start(sid, i)
        record_iteration_complete(
            row_id,
            verdict="not_met",
            judge_source="llm",
            judge_reason="t",
            ouroboros_verdict=verdict,
        )
    recent = recent_iteration_verdicts(sid, limit=3)
    # Legacy row excluded — only the two ouroboros rows show up.
    assert recent == ["falsified", "partial"]


# ---------------------------------------------------------------------
# GoalJudgeService.judge — Ouroboros mode dispatch
# ---------------------------------------------------------------------


def test_judge_dispatches_to_ouroboros_mode_when_hypothesis_supplied():
    """When both hypothesis + predicted are provided, the judge
    should call ``_run_ouroboros_judge`` and return a verdict with
    ``ouroboros_verdict`` populated.
    """
    captured = {}

    def fake_ouroboros(cls, goal, turn, h, p, backend, model):
        captured["called"] = True
        return JudgeVerdict(
            met=False,
            source="llm",
            reason="ok",
            ouroboros_verdict="falsified",
        )

    with patch.object(
        GoalJudgeService, "_run_ouroboros_judge", classmethod(fake_ouroboros)
    ):
        verdict = GoalJudgeService.judge(
            "goal",
            "turn text",
            hypothesis="h",
            predicted_outcome="p",
        )
    assert captured.get("called") is True
    assert verdict.ouroboros_verdict == "falsified"


def test_judge_falls_back_to_binary_mode_without_hypothesis():
    """Without hypothesis args, the judge runs the legacy
    ``_run_llm_judge`` path (no ouroboros_verdict set).
    """
    captured = {}

    def fake_legacy(cls, goal, turn, backend, model):
        captured["called"] = True
        return JudgeVerdict(met=True, source="llm", reason="ok")

    with patch.object(
        GoalJudgeService, "_run_llm_judge", classmethod(fake_legacy)
    ):
        verdict = GoalJudgeService.judge("goal", "turn text")
    assert captured.get("called") is True
    assert verdict.ouroboros_verdict is None


# ---------------------------------------------------------------------
# _parse_ouroboros_judge_json
# ---------------------------------------------------------------------


def test_parse_ouroboros_json_accepts_clean_response():
    out = _parse_ouroboros_judge_json(
        '{"met": false, "verdict": "falsified", "reason": "predicted X, got Y"}'
    )
    assert out is not None
    met, verdict, reason = out
    assert met is False
    assert verdict == "falsified"
    assert "predicted X" in reason


def test_parse_ouroboros_json_coerces_unknown_verdict():
    out = _parse_ouroboros_judge_json('{"met": true, "verdict": "bogus", "reason": "r"}')
    assert out is not None
    _, verdict, _ = out
    assert verdict == "unknown"


def test_parse_ouroboros_json_derives_met_from_verdict():
    out = _parse_ouroboros_judge_json('{"verdict": "confirmed", "reason": "ok"}')
    assert out is not None
    met, verdict, _ = out
    assert met is True
    assert verdict == "confirmed"
