"""Phase 6 (SkillOpt integration) — disjoint-split outcome measurement.

The gate optimizes against the ``eval`` partition; measure_outcome scores
before-vs-after on the ``train`` partition at the same seed (disjoint by
construction), the honest "did optimizing actually help" check. It is the only
real defense against the gate gaming itself.
"""

from __future__ import annotations

import json


def _seed_corpus(project_id: str, n: int = 12) -> None:
    from app.db import harness_kg_signals

    for i in range(n):
        harness_kg_signals.record_signal(
            signal_id=f"sig-{project_id}-{i}",
            project_id=project_id,
            question=f"How is concern {i} handled in the system?",
            content=f"By mechanism {i}.",
            round_id="r1",
            already_forged=False,
            weight=1.0,
            now="2026-01-01T00:00:00",
        )


def _answer_call(messages):
    sys = next((m["content"] for m in messages if m.get("role") == "system"), "")
    return "AFTER-answer" if "AFTER" in sys else "BEFORE-answer"


def _judge_favoring_after(messages):
    s = 0.9 if "AFTER-answer" in messages[0]["content"] else 0.4
    return json.dumps({"groundedness": s, "sufficiency": s, "quality": s, "reason": "x"})


def _judge_favoring_before(messages):
    s = 0.3 if "AFTER-answer" in messages[0]["content"] else 0.8
    return json.dumps({"groundedness": s, "sufficiency": s, "quality": s, "reason": "x"})


def test_measure_outcome_improved(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-o1")
    out = SkillSleepGate.measure_outcome(
        "proj-o1",
        before_body="BEFORE body",
        after_body="AFTER body",
        seed=5,
        n=8,
        answer_call=_answer_call,
        judge_call=_judge_favoring_after,
    )
    assert out["measured"] is True
    assert out["improved"] is True
    assert out["after_score"] > out["before_score"]
    assert out["question_count"] > 0


def test_measure_outcome_not_improved(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-o2")
    out = SkillSleepGate.measure_outcome(
        "proj-o2",
        before_body="BEFORE body",
        after_body="AFTER body",
        seed=5,
        n=8,
        answer_call=_answer_call,
        judge_call=_judge_favoring_before,
    )
    assert out["measured"] is True
    assert out["improved"] is False


def test_measure_outcome_uses_disjoint_partition(isolated_db, monkeypatch):
    """measure_outcome must score the TRAIN split — disjoint from the gate's
    EVAL split at the same seed, so no question overlaps the accept decision."""
    from app.services import skill_sleep_service as svc
    from app.services.answer_eval_service import AnswerEvalService

    _seed_corpus("proj-o3", n=20)
    seed = 9
    eval_qs = set(AnswerEvalService.build_question_set("proj-o3", n=8, partition="eval", seed=seed))

    seen: list[str] = []
    orig_score = svc._score_body

    def _spy(question, body, answer_fn, judge_fn):
        seen.append(question)
        return orig_score(question, body, answer_fn, judge_fn)

    monkeypatch.setattr(svc, "_score_body", _spy)
    svc.SkillSleepGate.measure_outcome(
        "proj-o3",
        before_body="B",
        after_body="A",
        seed=seed,
        n=8,
        answer_call=_answer_call,
        judge_call=_judge_favoring_after,
    )
    assert seen, "outcome should have scored questions"
    assert set(seen).isdisjoint(eval_qs), "outcome questions must not overlap the gate's eval set"


def test_measure_outcome_thin_corpus_unmeasured(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    out = SkillSleepGate.measure_outcome(
        "proj-thin-o",
        before_body="B",
        after_body="A",
        answer_call=_answer_call,
        judge_call=_judge_favoring_after,
    )
    assert out["measured"] is False
    assert out["improved"] is False


def test_measure_outcome_fails_closed_on_judge_error(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-o-err")

    def _boom(messages):
        raise RuntimeError("judge boom")

    out = SkillSleepGate.measure_outcome(
        "proj-o-err",
        before_body="B",
        after_body="A",
        seed=1,
        n=6,
        answer_call=_answer_call,
        judge_call=_boom,
    )
    assert out["measured"] is False
    assert out["improved"] is False


def test_evaluate_with_outcome_persists_measurement(isolated_db, monkeypatch):
    from app.db import skill_sleep
    from app.db.skills import add_user_skill
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-eo", n=16)
    add_user_skill("deploy", "", "d", 1)
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-eo"
    )
    # Candidate "AFTER" wins on both splits.
    v = SkillSleepGate.evaluate_skill_with_outcome(
        "proj-eo",
        "deploy",
        candidate_body="AFTER improved body",
        n=8,
        seed=4,
        answer_call=lambda m: (
            "AFTER-answer"
            if "AFTER" in next((x["content"] for x in m if x.get("role") == "system"), "")
            else "CURR-answer"
        ),
        judge_call=lambda m: json.dumps(
            {
                "groundedness": 0.9 if "AFTER-answer" in m[0]["content"] else 0.4,
                "sufficiency": 0.9 if "AFTER-answer" in m[0]["content"] else 0.4,
                "quality": 0.9 if "AFTER-answer" in m[0]["content"] else 0.4,
                "reason": "x",
            }
        ),
    )
    assert v["status"] == "accepted"
    assert "outcome" in v
    assert v["outcome"]["measured"] is True
    run = skill_sleep.get_run(v["run_id"])
    assert run["outcome_after_score"] is not None
    assert run["outcome_delta"] is not None


def test_migration_163_outcome_columns():
    import sqlite3

    from app.db.migrations import VERSIONED_MIGRATIONS
    from app.db.schema import create_fresh_schema

    assert 163 in {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(skill_sleep_runs)")}
    assert {
        "outcome_before_score",
        "outcome_after_score",
        "outcome_delta",
        "outcome_question_count",
    } <= cols
