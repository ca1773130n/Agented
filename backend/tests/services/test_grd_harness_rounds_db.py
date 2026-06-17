"""Tests for grd_harness_rounds mirror table + CRUD."""

from app.db.grd_harness_rounds import (
    get_harness_round,
    list_harness_rounds,
    upsert_harness_round,
)


def test_upsert_and_get_harness_round(isolated_db):
    from app.database import create_project as db_create_project

    pid = db_create_project(name="P")
    rid = upsert_harness_round(
        project_id=pid,
        round_id="20260614-120000",
        status="applied",
        detail="ok",
        evidence_count=12,
        patch_hash="abc",
        confidence=0.8,
        summary="tweak hypothesizer",
        applied_sha="deadbeef",
        eval_json='{"checks":[]}',
        patch_json='{"entries":[]}',
    )
    assert rid.startswith("hround-")
    got = get_harness_round(pid, "20260614-120000")
    assert got["status"] == "applied"
    assert got["confidence"] == 0.8
    assert got["round_id"] == "20260614-120000"
    assert got["eval"] == {"checks": []}


def test_upsert_is_idempotent_on_project_round(isolated_db):
    from app.database import create_project as db_create_project

    pid = db_create_project(name="P")
    upsert_harness_round(project_id=pid, round_id="r1", status="gathered")
    upsert_harness_round(project_id=pid, round_id="r1", status="applied", applied_sha="sha1")
    rounds = list_harness_rounds(pid)
    assert len(rounds) == 1
    assert rounds[0]["status"] == "applied"
    assert rounds[0]["applied_sha"] == "sha1"


def test_list_harness_rounds_newest_first(isolated_db):
    from app.database import create_project as db_create_project

    pid = db_create_project(name="P")
    upsert_harness_round(project_id=pid, round_id="20260614-100000", status="applied")
    upsert_harness_round(project_id=pid, round_id="20260614-110000", status="applied")
    rounds = list_harness_rounds(pid)
    assert [r["round_id"] for r in rounds] == ["20260614-110000", "20260614-100000"]
