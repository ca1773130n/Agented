"""Phase 5b (SkillOpt integration) — periodic Skill-Sleep scheduler.

SkillSleepScheduler.run_due drives a staged round for each (project, skill)
that is bound to an autonomy-enabled project and past its cooldown. Staged
only — never auto-adopts; one round failure is isolated, never raised.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def test_run_due_runs_eligible_pairs(isolated_db):
    from app.services.skill_sleep_service import SkillSleepScheduler

    ran_for = []

    def _round(pid, sk):
        ran_for.append((pid, sk))
        return {"status": "accepted"}

    res = SkillSleepScheduler.run_due(
        eligible_fn=lambda: [("proj-a", "s1"), ("proj-b", "s2")],
        round_fn=_round,
    )
    assert ran_for == [("proj-a", "s1"), ("proj-b", "s2")]
    assert len(res["ran"]) == 2
    assert res["ran"][0]["status"] == "accepted"


def test_run_due_respects_cooldown(isolated_db):
    from app.db import skill_sleep
    from app.services.skill_sleep_service import SkillSleepScheduler

    # A run created "now" → still within a 24h cooldown.
    rid = skill_sleep.create_run("proj-cd", "s1")
    skill_sleep.finalize_run(rid, status="rejected", current_score=0.5, candidate_score=0.4)

    ran = []
    res = SkillSleepScheduler.run_due(
        now=datetime.utcnow(),
        cooldown_hours=24,
        eligible_fn=lambda: [("proj-cd", "s1")],
        round_fn=lambda pid, sk: ran.append((pid, sk)) or {"status": "x"},
    )
    assert ran == [], "within cooldown → must skip"
    assert res["skipped"] and res["skipped"][0]["reason"] == "cooldown"


def test_run_due_runs_after_cooldown_elapsed(isolated_db):
    from app.db import skill_sleep
    from app.services.skill_sleep_service import SkillSleepScheduler

    rid = skill_sleep.create_run("proj-old", "s1")
    skill_sleep.finalize_run(rid, status="rejected", current_score=0.5, candidate_score=0.4)

    ran = []
    # Evaluate "now" as 48h in the future → cooldown elapsed.
    res = SkillSleepScheduler.run_due(
        now=datetime.utcnow() + timedelta(hours=48),
        cooldown_hours=24,
        eligible_fn=lambda: [("proj-old", "s1")],
        round_fn=lambda pid, sk: ran.append((pid, sk)) or {"status": "accepted"},
    )
    assert ran == [("proj-old", "s1")]
    assert len(res["ran"]) == 1


def test_run_due_max_per_run_caps(isolated_db):
    from app.services.skill_sleep_service import SkillSleepScheduler

    pairs = [(f"p{i}", "s") for i in range(20)]
    ran = []
    SkillSleepScheduler.run_due(
        eligible_fn=lambda: pairs,
        round_fn=lambda pid, sk: ran.append(pid) or {"status": "x"},
        max_per_run=3,
    )
    assert len(ran) == 3


def test_run_due_isolates_round_failure(isolated_db):
    from app.services.skill_sleep_service import SkillSleepScheduler

    def _round(pid, sk):
        if pid == "boom":
            raise RuntimeError("round exploded")
        return {"status": "accepted"}

    res = SkillSleepScheduler.run_due(
        eligible_fn=lambda: [("boom", "s"), ("ok", "s")],
        round_fn=_round,
    )
    # The failure is skipped, the next pair still runs.
    assert any(s["reason"] == "error" for s in res["skipped"])
    assert any(r["project_id"] == "ok" for r in res["ran"])


def test_discover_eligible_finds_bound_skills(isolated_db):
    from app.db import project_autonomy_config as cfg
    from app.db import project_forge_bindings as fb
    from app.db.connection import get_connection
    from app.db.skills import add_user_skill
    from app.models.autonomy_policy import AutonomyPolicy
    from app.services.skill_sleep_service import _discover_eligible_skills

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES ('proj-disc','D')")
        conn.commit()
    cfg.upsert_policy("proj-disc", AutonomyPolicy(enabled=True))
    sid = add_user_skill("deploy", "/tmp/x/SKILL.md", "d", 1)
    fb.add_binding("proj-disc", "skill", str(sid))

    pairs = _discover_eligible_skills()
    assert ("proj-disc", "deploy") in pairs


def test_nightly_job_is_registered_and_safe(isolated_db):
    """The lifecycle periodic job exists and never raises."""
    from app_litestar import lifecycle

    # No autonomy-enabled projects → empty run, no exception.
    lifecycle.skill_sleep_nightly_job()
