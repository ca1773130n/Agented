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


def test_evaluate_skill_requires_project_binding(isolated_db, tmp_path, monkeypatch):
    """A skill not bound to the project → SkillNotInProjectError (codex HIGH)."""
    from app.db.skills import add_user_skill
    from app.services.skill_sleep_service import SkillNotInProjectError, SkillSleepGate

    _seed_corpus("proj-orch")
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("CURR current body\n", encoding="utf-8")
    add_user_skill("deploy", str(skill_md), "d", 1)
    # No forge binding → not owned by proj-orch.
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: None
    )
    import pytest

    with pytest.raises(SkillNotInProjectError):
        SkillSleepGate.evaluate_skill(
            "proj-orch", "deploy", candidate_body="x", answer_call=_answer_call
        )


def test_evaluate_skill_reads_current_body_when_bound(isolated_db, tmp_path, monkeypatch):
    from app.db.skills import add_user_skill
    from app.services.skill_sleep_service import SkillSleepGate

    _seed_corpus("proj-orch2")
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text('---\nname: "deploy"\n---\n\nCURR current body\n', encoding="utf-8")
    add_user_skill("deploy", str(skill_md), "d", 1)
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-orch2"
    )

    v = SkillSleepGate.evaluate_skill(
        "proj-orch2",
        "deploy",
        candidate_body="CAND improved body",
        answer_call=_answer_call,
        judge_call=_judge_favoring_candidate,
        n=6,
        seed=2,
    )
    assert v["status"] == "accepted"
    from app.db import skill_sleep

    run = skill_sleep.get_run(v["run_id"])
    assert run["candidate_body"] == "CAND improved body"
    assert run["adopted_at"] is None
    assert run["current_body_hash"] is not None


def _accepted_run(project_id: str, skill_id: int, *, body: str, current_hash: str) -> int:
    from app.db import skill_sleep

    run_id = skill_sleep.create_run(project_id, "deploy", skill_id=skill_id)
    skill_sleep.finalize_run(
        run_id,
        status="accepted",
        current_score=0.4,
        candidate_score=0.9,
        question_count=6,
        candidate_body=body,
        current_body_hash=current_hash,
    )
    return run_id


def test_adopt_run_writes_when_confirmed(isolated_db, monkeypatch):
    from app.db import skill_sleep
    from app.services import skill_sleep_service as svc

    # current_body_hash of an empty/missing file (skill_path None → "").
    run_id = _accepted_run("proj-ad", 42, body="ADOPTED BODY", current_hash=svc._body_hash(""))

    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-ad"
    )
    monkeypatch.setattr("app.db.skills.get_user_skill", lambda sid: {"skill_path": None})
    calls = []

    def _ok_update(*, asset_id, payload):
        calls.append((asset_id, payload))
        return True  # confirmed write

    monkeypatch.setattr("app.services.harness_evolver._update_skill", _ok_update)

    res = svc.SkillSleepGate.adopt_run(run_id)
    assert res["adopted"] is True
    assert calls == [(42, {"content": "ADOPTED BODY"})]
    assert skill_sleep.get_run(run_id)["adopted_at"] is not None

    # Idempotent.
    res2 = svc.SkillSleepGate.adopt_run(run_id)
    assert res2["adopted"] is True
    assert len(calls) == 1


def test_adopt_run_not_marked_when_write_refused(isolated_db, monkeypatch):
    """_update_skill returning False (containment refusal) must NOT stamp
    adopted_at (codex review HIGH)."""
    from app.db import skill_sleep
    from app.services import skill_sleep_service as svc

    run_id = _accepted_run("proj-ref", 7, body="BODY", current_hash=svc._body_hash(""))
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-ref"
    )
    monkeypatch.setattr("app.db.skills.get_user_skill", lambda sid: {"skill_path": None})
    monkeypatch.setattr(
        "app.services.harness_evolver._update_skill", lambda *, asset_id, payload: False
    )

    res = svc.SkillSleepGate.adopt_run(run_id)
    assert res["adopted"] is False
    assert skill_sleep.get_run(run_id)["adopted_at"] is None


def test_adopt_run_refuses_stale(isolated_db, monkeypatch):
    """If the skill body changed since gating, adopt refuses (codex MEDIUM)."""
    from app.services import skill_sleep_service as svc

    # Run pinned a DIFFERENT hash than the live body.
    run_id = _accepted_run("proj-stale", 9, body="BODY", current_hash="deadbeef-old-hash")
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-stale"
    )
    monkeypatch.setattr("app.db.skills.get_user_skill", lambda sid: {"skill_path": None})
    wrote = []
    monkeypatch.setattr(
        "app.services.harness_evolver._update_skill",
        lambda *, asset_id, payload: wrote.append(1) or True,
    )

    res = svc.SkillSleepGate.adopt_run(run_id)
    assert res["adopted"] is False
    assert "stale" in res["reason"]
    assert not wrote, "stale run must not write"


def test_adopt_run_refuses_foreign_project(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc

    run_id = _accepted_run("proj-own", 11, body="BODY", current_hash=svc._body_hash(""))
    # Skill is now owned by a DIFFERENT project.
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-other"
    )
    res = svc.SkillSleepGate.adopt_run(run_id)
    assert res["adopted"] is False
    assert "bound" in res["reason"]


def test_adopt_run_refuses_non_accepted(isolated_db):
    from app.db import skill_sleep
    from app.services.skill_sleep_service import SkillSleepGate

    run_id = skill_sleep.create_run("proj-ad2", "s", skill_id=1)
    skill_sleep.finalize_run(run_id, status="rejected", candidate_score=0.1, current_score=0.5)
    res = SkillSleepGate.adopt_run(run_id)
    assert res["adopted"] is False
    assert "not adoptable" in res["reason"]

    assert SkillSleepGate.adopt_run(999999)["adopted"] is False


def test_adopt_migrations_161_162_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    assert 161 in versions
    assert 162 in versions

    import sqlite3

    from app.db.schema import create_fresh_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(skill_sleep_runs)")}
    assert "adopted_at" in cols
    assert "current_body_hash" in cols
