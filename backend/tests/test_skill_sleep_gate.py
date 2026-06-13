"""Phase 2 (SkillOpt integration) — the Skill-Sleep validation gate.

SkillSleepGate.evaluate_candidate blind-judges the CURRENT skill body (arm A)
vs a CANDIDATE body (arm B) over a held-out question partition, accepting the
candidate only on STRICT improvement. Fails CLOSED on judge/infra error and
ABSTAINS (→reject) when the corpus is too thin to judge.
"""

from __future__ import annotations

import json


def _seed_corpus(project_id: str, n: int = 10) -> None:
    """Seed enough durable signals that corpus_health is healthy (>= 8)."""
    from app.db import harness_kg_signals

    for i in range(n):
        harness_kg_signals.record_signal(
            signal_id=f"sig-{project_id}-{i}",
            project_id=project_id,
            question=f"How is concern {i} handled in the system?",
            content=f"It is handled by mechanism {i}.",
            round_id="r1",
            already_forged=False,
            weight=1.0,
            now="2026-01-01T00:00:00",
        )


def _answer_call(messages):
    """Echo which body is in context so the judge can score per-arm."""
    sys = next((m["content"] for m in messages if m.get("role") == "system"), "")
    return "CAND-answer" if "CAND" in sys else "CURR-answer"


def _judge_favoring_candidate(messages):
    prompt = messages[0]["content"]
    s = 0.9 if "CAND-answer" in prompt else 0.4
    return json.dumps({"groundedness": s, "sufficiency": s, "quality": s, "reason": "x"})


def _judge_favoring_current(messages):
    prompt = messages[0]["content"]
    s = 0.3 if "CAND-answer" in prompt else 0.8
    return json.dumps({"groundedness": s, "sufficiency": s, "quality": s, "reason": "x"})


def test_accepts_when_candidate_strictly_improves(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-acc")
    v = SkillSleepGate.evaluate_candidate(
        "proj-acc",
        skill_name="deploy-helper",
        current_body="CURR body",
        candidate_body="CAND body",
        answer_call=_answer_call,
        judge_call=_judge_favoring_candidate,
        n=6,
        seed=3,
    )
    assert v["status"] == "accepted"
    assert v["accepted"] is True
    assert v["candidate_score"] > v["current_score"]
    assert v["question_count"] > 0
    # A run row was persisted with the verdict.
    from app.db import skill_sleep

    assert skill_sleep.get_run(v["run_id"])["status"] == "accepted"


def test_rejects_when_not_strictly_better(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-rej")
    v = SkillSleepGate.evaluate_candidate(
        "proj-rej",
        skill_name="deploy-helper",
        current_body="CURR body",
        candidate_body="CAND body",
        answer_call=_answer_call,
        judge_call=_judge_favoring_current,
        n=6,
        seed=3,
    )
    assert v["status"] == "rejected"
    assert v["accepted"] is False
    assert v["candidate_score"] <= v["current_score"]


def test_abstains_when_corpus_thin(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    # No corpus seeded → corpus_health unhealthy → abstain (treated as reject).
    v = SkillSleepGate.evaluate_candidate(
        "proj-thin",
        skill_name="s",
        current_body="CURR",
        candidate_body="CAND",
        answer_call=_answer_call,
        judge_call=_judge_favoring_candidate,
    )
    assert v["status"] == "abstained"
    assert v["accepted"] is False
    assert "corpus" in (v["reason"] or "").lower()


def test_fails_closed_on_judge_error(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-fail")

    def _boom(messages):
        raise RuntimeError("judge exploded")

    v = SkillSleepGate.evaluate_candidate(
        "proj-fail",
        skill_name="s",
        current_body="CURR",
        candidate_body="CAND",
        answer_call=_answer_call,
        judge_call=_boom,
        n=4,
        seed=1,
    )
    # Fail CLOSED: no exception escapes, verdict is non-accept.
    assert v["accepted"] is False
    assert v["status"] in ("failed", "rejected")


def test_judge_prompt_is_blind(isolated_db):
    """The judge must never see which arm (current/candidate) it is scoring."""
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-blind")
    seen = []

    def _capturing_judge(messages):
        seen.append(messages[0]["content"])
        return json.dumps({"groundedness": 0.5, "sufficiency": 0.5, "quality": 0.5, "reason": "x"})

    SkillSleepGate.evaluate_candidate(
        "proj-blind",
        skill_name="s",
        current_body="CURR",
        candidate_body="CAND",
        answer_call=_answer_call,
        judge_call=_capturing_judge,
        n=4,
        seed=1,
    )
    assert seen, "judge should have been called"
    for prompt in seen:
        low = prompt.lower()
        assert "candidate" not in low
        assert "current skill" not in low
        assert "arm a" not in low and "arm b" not in low


def test_nan_judge_score_fails_closed(isolated_db):
    """A judge emitting NaN must NOT clamp to a perfect 1.0 and accept — strict
    parse rejects non-finite values → fail closed (codex review HIGH)."""
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-nan")

    def _nan_for_candidate(messages):
        if "CAND-answer" in messages[0]["content"]:
            return '{"groundedness": NaN, "sufficiency": NaN, "quality": NaN, "reason": "x"}'
        return '{"groundedness": 0.3, "sufficiency": 0.3, "quality": 0.3, "reason": "x"}'

    v = SkillSleepGate.evaluate_candidate(
        "proj-nan",
        skill_name="s",
        current_body="CURR",
        candidate_body="CAND",
        answer_call=_answer_call,
        judge_call=_nan_for_candidate,
        n=4,
        seed=1,
    )
    assert v["accepted"] is False
    assert v["status"] == "failed"


def test_malformed_judge_fails_closed(isolated_db):
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-malformed")
    v = SkillSleepGate.evaluate_candidate(
        "proj-malformed",
        skill_name="s",
        current_body="CURR",
        candidate_body="CAND",
        answer_call=_answer_call,
        judge_call=lambda m: "not json at all",
        n=4,
        seed=1,
    )
    assert v["accepted"] is False
    assert v["status"] == "failed"


def test_unexpected_error_finalizes_run_failed(isolated_db, monkeypatch):
    """An error after create_run (e.g. build_question_set) must finalize the
    run as failed, never leave it 'running' (codex review MEDIUM)."""
    from app.db import skill_sleep
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-boom")
    monkeypatch.setattr(
        "app.services.answer_eval_service.AnswerEvalService.build_question_set",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))),
    )
    v = SkillSleepGate.evaluate_candidate(
        "proj-boom",
        skill_name="s",
        current_body="CURR",
        candidate_body="CAND",
        answer_call=_answer_call,
        judge_call=_judge_favoring_candidate,
    )
    assert v["status"] == "failed"
    assert skill_sleep.get_run(v["run_id"])["status"] == "failed"
