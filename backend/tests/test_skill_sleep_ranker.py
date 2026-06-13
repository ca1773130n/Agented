"""Phase 3 (SkillOpt integration) — edit-budget ranker (textual learning rate).

rank_edits decomposes candidate-vs-current into discrete edits, scores each
edit's marginal contribution on the eval split (cheap-model seams), and keeps
the top-N within budget. The diff/apply primitives are pure; only ranking
calls the LLM seams.
"""

from __future__ import annotations

import json


def _seed_corpus(project_id: str, n: int = 12) -> None:
    from app.db import harness_kg_signals

    for i in range(n):
        harness_kg_signals.record_signal(
            signal_id=f"sig-{project_id}-{i}",
            project_id=project_id,
            question=f"How is concern {i} handled?",
            content=f"By mechanism {i}.",
            round_id="r1",
            already_forged=False,
            weight=1.0,
            now="2026-01-01T00:00:00",
        )


# ---- pure diff/apply primitives ----


def test_apply_all_edits_reproduces_candidate():
    from app.services.skill_sleep_service import _apply_edits, _diff_opcodes

    cur = "line A\nline B\nline C"
    cand = "line A\nCHANGED B\nline C\nNEW D"
    c, d, ops, edits = _diff_opcodes(cur, cand)
    assert len(edits) >= 1
    assert _apply_edits(c, d, ops, set(edits)) == cand
    # Applying none reproduces the current body.
    assert _apply_edits(c, d, ops, set()) == cur


def test_apply_subset_mixes():
    from app.services.skill_sleep_service import _apply_edits, _diff_opcodes

    cur = "keep1\nold2\nkeep3"
    cand = "keep1\nnew2\nkeep3"
    c, d, ops, edits = _diff_opcodes(cur, cand)
    # Apply the single edit → candidate; the body is well-formed either way.
    applied = _apply_edits(c, d, ops, set(edits))
    assert "new2" in applied and "old2" not in applied


# ---- ranker ----


def _answer(messages):
    """Answer echoes whichever 'GOODEDIT' marker the body carries."""
    sys = next((m["content"] for m in messages if m.get("role") == "system"), "")
    return "WIN" if "GOODEDIT" in sys else "MEH"


def _judge(messages):
    s = 0.9 if "WIN" in messages[0]["content"] else 0.4
    return json.dumps({"groundedness": s, "sufficiency": s, "quality": s, "reason": "x"})


def test_rank_edits_noop_when_within_budget(isolated_db):
    from app.services.skill_sleep_service import rank_edits

    _seed_corpus("proj-rk1")
    cur = "a\nb\nc"
    cand = "a\nB2\nc"  # one edit
    out = rank_edits(
        "proj-rk1", cur, cand, budget=4, seed=1, n=4, answer_call=_answer, judge_call=_judge
    )
    assert out == cand  # <= budget → unchanged


def test_rank_edits_keeps_top_contributing_edit(isolated_db):
    from app.services.skill_sleep_service import rank_edits

    _seed_corpus("proj-rk2")
    # Two disjoint edits; only the GOODEDIT one improves the score.
    cur = "intro\nold-one\nmiddle\nold-two\nend"
    cand = "intro\nGOODEDIT one\nmiddle\nnoise two\nend"
    out = rank_edits(
        "proj-rk2", cur, cand, budget=1, seed=1, n=4, answer_call=_answer, judge_call=_judge
    )
    # Budget 1 → keep the higher-marginal edit (GOODEDIT), drop the other.
    assert "GOODEDIT one" in out
    assert "noise two" not in out
    assert "old-two" in out  # unselected edit reverts to current


def test_rank_edits_fail_open_on_scoring_error(isolated_db):
    from app.services.skill_sleep_service import rank_edits

    _seed_corpus("proj-rk3")
    cur = "a\nb\nc\nd\ne"
    cand = "A2\nB2\nC2\nD2\nE2"  # many edits > budget

    def _boom(m):
        raise RuntimeError("judge boom")

    out = rank_edits(
        "proj-rk3", cur, cand, budget=2, seed=1, n=4, answer_call=_answer, judge_call=_boom
    )
    # Fail-open: scoring error → return the full candidate (gate is the safety).
    assert out == cand


def test_round_with_edit_budget_trims_before_gate(isolated_db, monkeypatch):
    from app.db.skills import add_user_skill
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-rk-round", n=16)
    add_user_skill("deploy", "", "d", 1)
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-rk-round"
    )

    gated_bodies = []
    orig = SkillSleepGate.evaluate_skill_with_outcome

    def _spy(project_id, skill_name, *, candidate_body, **kw):
        gated_bodies.append(candidate_body)
        return orig(project_id, skill_name, candidate_body=candidate_body, **kw)

    monkeypatch.setattr(SkillSleepGate, "evaluate_skill_with_outcome", staticmethod(_spy))

    # Reflect proposes a multi-edit body; budget=1 should trim it before the gate.
    SkillSleepGate.run_skill_sleep_round(
        "proj-rk-round",
        "deploy",
        reflect_call=lambda m: "GOODEDIT one\nnoise two\nnoise three",
        answer_call=_answer,
        judge_call=_judge,
        n=4,
        seed=2,
        edit_budget=1,
    )
    assert gated_bodies, "the gate should have been invoked with a (trimmed) candidate"
    # The gated body keeps the winning edit.
    assert "GOODEDIT one" in gated_bodies[0]
