"""Phase 4 (SkillOpt integration) — orchestrate + operator-adopt.

evaluate_skill resolves the skill's current on-disk body and gates a candidate
against it (no write). adopt_run writes an ACCEPTED run's staged body to disk
via the evolver's containment-checked _update_skill, then stamps adopted_at.
"""

from __future__ import annotations

import json


def _seed_corpus(project_id: str, n: int = 10) -> None:
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


def _answer_call(messages):
    sys = next((m["content"] for m in messages if m.get("role") == "system"), "")
    return "CAND-answer" if "CAND" in sys else "CURR-answer"


def _judge_favoring_candidate(messages):
    s = 0.9 if "CAND-answer" in messages[0]["content"] else 0.4
    return json.dumps({"groundedness": s, "sufficiency": s, "quality": s, "reason": "x"})


def test_strip_frontmatter():
    from app.services.skill_sleep_service import _strip_frontmatter

    doc = '---\nname: "x"\ndescription: "y"\n---\n\nThe real body here.\n'
    assert _strip_frontmatter(doc) == "The real body here.\n"
    assert _strip_frontmatter("no frontmatter") == "no frontmatter"


def test_evaluate_skill_reads_current_body_from_disk(isolated_db, tmp_path):
    from app.db.skills import add_user_skill
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-orch")
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text('---\nname: "deploy"\n---\n\nCURR current body\n', encoding="utf-8")
    add_user_skill("deploy", str(skill_md), "d", 1)

    v = SkillSleepGate.evaluate_skill(
        "proj-orch",
        "deploy",
        candidate_body="CAND improved body",
        answer_call=_answer_call,
        judge_call=_judge_favoring_candidate,
        n=6,
        seed=2,
    )
    assert v["status"] == "accepted"
    # The run persisted the staged candidate for adoption.
    from app.db import skill_sleep

    run = skill_sleep.get_run(v["run_id"])
    assert run["candidate_body"] == "CAND improved body"
    assert run["adopted_at"] is None


def test_adopt_run_writes_accepted_candidate(isolated_db, monkeypatch):
    from app.db import skill_sleep
    from app.services import skill_sleep_service as svc

    run_id = skill_sleep.create_run("proj-ad", "deploy", skill_id=42)
    skill_sleep.finalize_run(
        run_id,
        status="accepted",
        current_score=0.4,
        candidate_score=0.9,
        question_count=6,
        candidate_body="ADOPTED BODY",
    )

    calls = []
    monkeypatch.setattr(
        "app.services.harness_evolver._update_skill",
        lambda *, asset_id, payload: calls.append((asset_id, payload)),
    )

    res = svc.SkillSleepGate.adopt_run(run_id)
    assert res["adopted"] is True
    assert calls == [(42, {"content": "ADOPTED BODY"})]
    assert skill_sleep.get_run(run_id)["adopted_at"] is not None

    # Idempotent: a second adopt is a no-op write but still reports adopted.
    res2 = svc.SkillSleepGate.adopt_run(run_id)
    assert res2["adopted"] is True
    assert len(calls) == 1, "second adopt must not write again"


def test_adopt_run_refuses_non_accepted(isolated_db):
    from app.db import skill_sleep
    from app.services.skill_sleep_service import SkillSleepGate

    run_id = skill_sleep.create_run("proj-ad2", "s", skill_id=1)
    skill_sleep.finalize_run(run_id, status="rejected", candidate_score=0.1, current_score=0.5)
    res = SkillSleepGate.adopt_run(run_id)
    assert res["adopted"] is False
    assert "not adoptable" in res["reason"]

    assert SkillSleepGate.adopt_run(999999)["adopted"] is False


def test_adopt_migration_161_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    assert 161 in versions

    # adopted_at present in fresh schema too.
    import sqlite3

    from app.db.schema import create_fresh_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(skill_sleep_runs)")}
    assert "adopted_at" in cols
