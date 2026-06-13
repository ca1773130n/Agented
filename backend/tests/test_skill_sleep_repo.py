"""Tests for the skill_sleep_runs store (SkillOpt integration, migration 160)."""

from __future__ import annotations

import sqlite3

import pytest

from app.db import skill_sleep


def test_migration_160_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 160 in versions
    assert "skill_sleep" in names


def test_fresh_schema_has_skill_sleep_table():
    from app.db.schema import create_fresh_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "skill_sleep_runs" in tables


def test_run_lifecycle_accepted():
    run_id = skill_sleep.create_run(
        "proj-ss", "deploy-helper", skill_id=3, partition_seed=7, judge_backend="claude"
    )
    assert isinstance(run_id, int) and run_id > 0
    assert skill_sleep.get_run(run_id)["status"] == "running"

    ok = skill_sleep.finalize_run(
        run_id,
        status="accepted",
        current_score=0.60,
        candidate_score=0.74,
        question_count=6,
        candidate_body="# improved skill\n",
        reason="candidate strictly improved",
    )
    assert ok is True

    run = skill_sleep.get_run(run_id)
    assert run["status"] == "accepted"
    assert run["current_score"] == pytest.approx(0.60)
    assert run["candidate_score"] == pytest.approx(0.74)
    assert run["delta"] == pytest.approx(0.14)
    assert run["question_count"] == 6
    assert run["finished_at"] is not None


def test_status_check_rejects_bad_value():
    run_id = skill_sleep.create_run("proj-ss2", "s")
    with pytest.raises(sqlite3.IntegrityError):
        skill_sleep.finalize_run(run_id, status="bogus")


def test_list_runs_project_scoped_and_ordered():
    skill_sleep.create_run("proj-A", "s1")
    skill_sleep.create_run("proj-A", "s2")
    skill_sleep.create_run("proj-B", "s3")
    a = skill_sleep.list_runs("proj-A")
    assert len(a) == 2
    assert all(r["project_id"] == "proj-A" for r in a)
    assert skill_sleep.get_run(999999) is None
