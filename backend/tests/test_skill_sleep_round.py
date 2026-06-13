"""Phase 5 (SkillOpt integration) — Reflect + autonomous round.

propose_candidate is the Reflect stage: read the project's recurring needs +
current SKILL.md, ask an optimizer (injected seam) for an improved body.
run_skill_sleep_round chains Reflect → gate → outcome measure, staging the
result for operator adoption (never auto-applied).
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


def test_propose_candidate_returns_improved_body(isolated_db):
    from app.services.skill_sleep_service import propose_candidate

    _seed_corpus("proj-r1")
    cand = propose_candidate(
        "proj-r1",
        "deploy",
        "old body",
        reflect_call=lambda m: "IMPROVED skill body addressing concerns",
    )
    assert cand == "IMPROVED skill body addressing concerns"


def test_propose_candidate_strips_code_fence(isolated_db):
    from app.services.skill_sleep_service import propose_candidate

    _seed_corpus("proj-r2")
    cand = propose_candidate(
        "proj-r2",
        "deploy",
        "old",
        reflect_call=lambda m: "```markdown\nfenced new body\n```",
    )
    assert cand == "fenced new body"


def test_propose_candidate_none_when_unchanged(isolated_db):
    from app.services.skill_sleep_service import propose_candidate

    _seed_corpus("proj-r3")
    assert (
        propose_candidate("proj-r3", "deploy", "same body", reflect_call=lambda m: "same body")
        is None
    )


def test_propose_candidate_none_on_reflect_error(isolated_db):
    from app.services.skill_sleep_service import propose_candidate

    _seed_corpus("proj-r4")

    def _boom(m):
        raise RuntimeError("reflect boom")

    assert propose_candidate("proj-r4", "deploy", "x", reflect_call=_boom) is None


def test_propose_candidate_context_includes_project_needs(isolated_db):
    """The reflect prompt must surface the project's recurring questions."""
    from app.services.skill_sleep_service import propose_candidate

    _seed_corpus("proj-r5", n=3)
    seen = {}

    def _capture(messages):
        seen["prompt"] = messages[0]["content"]
        return "new body"

    propose_candidate("proj-r5", "deploy", "old", reflect_call=_capture)
    assert "concern 0" in seen["prompt"] or "How is concern" in seen["prompt"]


def test_run_round_accepts_winning_candidate(isolated_db, monkeypatch):
    from app.db import skill_sleep
    from app.db.skills import add_user_skill
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-round", n=16)
    add_user_skill("deploy", "", "d", 1)
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-round"
    )

    def _answer(messages):
        sys = next((m["content"] for m in messages if m.get("role") == "system"), "")
        return "CAND-answer" if "CAND" in sys else "CURR-answer"

    def _judge(messages):
        s = 0.9 if "CAND-answer" in messages[0]["content"] else 0.4
        return json.dumps({"groundedness": s, "sufficiency": s, "quality": s, "reason": "x"})

    v = SkillSleepGate.run_skill_sleep_round(
        "proj-round",
        "deploy",
        reflect_call=lambda m: "CAND improved body",
        answer_call=_answer,
        judge_call=_judge,
        n=8,
        seed=4,
    )
    assert v["status"] == "accepted"
    assert v["accepted"] is True
    assert "outcome" in v  # measured by default
    # Staged, NOT auto-adopted.
    assert skill_sleep.get_run(v["run_id"])["adopted_at"] is None


def test_run_round_no_candidate_is_noop(isolated_db, monkeypatch):
    from app.db.skills import add_user_skill
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-round2", n=12)
    add_user_skill("deploy", "", "d", 1)
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-round2"
    )
    # Reflect proposes nothing new (empty current body, returns empty).
    v = SkillSleepGate.run_skill_sleep_round(
        "proj-round2",
        "deploy",
        reflect_call=lambda m: "",
        n=6,
        seed=1,
    )
    assert v["status"] == "no_candidate"
    assert v["accepted"] is False
    assert v["run_id"] is None


def test_run_round_requires_project_binding(isolated_db, monkeypatch):
    from app.db.skills import add_user_skill
    from app.services.skill_sleep_service import SkillNotInProjectError, SkillSleepGate

    _seed_corpus("proj-round3")
    add_user_skill("deploy", "", "d", 1)
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: None
    )
    import pytest

    with pytest.raises(SkillNotInProjectError):
        SkillSleepGate.run_skill_sleep_round("proj-round3", "deploy", reflect_call=lambda m: "x")
