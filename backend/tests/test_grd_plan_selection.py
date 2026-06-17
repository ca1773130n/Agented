"""GRD 0.4.5 multi-candidate plan selection (milestone sub-project #3).

The `gd` CLI is mocked at GrdCliService.run_gd_json; DB exercised against
``isolated_db``. Covers select_candidate argv (dry-run vs promote, force,
verification), mirror-only-on-real-run, plan_tournament argv, and the DB
upsert/get round-trip.
"""

from __future__ import annotations

from unittest.mock import patch

from app.db import get_plan_selection, upsert_plan_selection
from app.services import grd_plan_selection_runner as runner


_SELECTION = {
    "phase": "3",
    "milestone": "v0.6",
    "candidates": [
        {"relPath": "phases/03/PLAN-1.md", "total_score": 1.1},
        {"relPath": "phases/03/PLAN-2.md", "total_score": 2.4},
    ],
    "winner": {"relPath": "phases/03/PLAN-2.md", "total_score": 2.4},
    "promoted_to": "phases/03/PLAN.md",
    "audit_trail_path": "phases/03/PLAN-SELECTION.json",
}


def _ok(data):
    return {"success": True, "data": data, "error": None}


# ---- select_candidate argv ----------------------------------------------

def test_select_dry_run_argv_and_no_mirror(isolated_db):
    cap = {}
    with patch.object(
        runner.GrdCliService, "run_gd_json",
        side_effect=lambda cwd, *a: cap.update(args=a) or _ok({**_SELECTION, "promoted_to": None}),
    ):
        res = runner.select_candidate("proj-x", "/cwd", "3", dry_run=True)
    assert cap["args"] == ("select-candidate", "3", "--dry-run")
    assert res["success"] is True
    assert res["mirrored"] is None  # dry-run never mirrors
    assert get_plan_selection("proj-x", "3") is None


def test_select_real_run_promotes_and_mirrors(isolated_db):
    from app.db.projects import create_project

    pid = create_project("SelReal")
    cap = {}
    with patch.object(
        runner.GrdCliService, "run_gd_json",
        side_effect=lambda cwd, *a: cap.update(args=a) or _ok(_SELECTION),
    ):
        res = runner.select_candidate(pid, "/cwd", "3")
    assert cap["args"] == ("select-candidate", "3")  # no --dry-run
    assert res["mirrored"] and res["mirrored"].startswith("psel-")
    row = get_plan_selection(pid, "3")
    assert row is not None
    assert row["winner_rel"] == "phases/03/PLAN-2.md"
    assert row["promoted_to"] == "phases/03/PLAN.md"
    assert len(row["candidates"]) == 2


def test_select_force_and_verification_flags(isolated_db):
    cap = {}
    with patch.object(
        runner.GrdCliService, "run_gd_json",
        side_effect=lambda cwd, *a: cap.update(args=a) or _ok(_SELECTION),
    ):
        runner.select_candidate(
            "p", "/cwd", "5", force=True, run_verification_commands=True
        )
    assert cap["args"] == (
        "select-candidate", "5", "--force", "--run-verification-commands",
    )


def test_select_failure_surfaces_error_no_mirror(isolated_db):
    with patch.object(
        runner.GrdCliService, "run_gd_json",
        return_value={"success": False, "data": None, "error": "no PLAN-N.md candidates found"},
    ):
        res = runner.select_candidate("p", "/cwd", "9")
    assert res["success"] is False
    assert "no PLAN-N.md candidates" in res["error"]
    assert res["mirrored"] is None


# ---- plan_tournament argv -----------------------------------------------

def test_plan_tournament_argv(isolated_db):
    cap = {}
    with patch.object(
        runner.GrdCliService, "run_gd_json",
        side_effect=lambda cwd, *a: cap.update(args=a) or _ok({"ranked": [], "winner": None}),
    ):
        runner.plan_tournament("/cwd", "2", ["a/PLAN-1.md", "b/PLAN-2.md"])
    assert cap["args"] == (
        "plan-tournament", "--phase", "2", "--candidates", "a/PLAN-1.md", "b/PLAN-2.md",
    )


# ---- DB mirror round-trip ------------------------------------------------

def test_upsert_plan_selection_is_full_replace(isolated_db):
    from app.db.projects import create_project

    pid = create_project("Upsert")
    a = upsert_plan_selection(project_id=pid, phase="1", winner_rel="PLAN-1.md")
    b = upsert_plan_selection(project_id=pid, phase="1", winner_rel="PLAN-2.md")
    assert a == b  # stable id across upserts on (project_id, phase)
    assert get_plan_selection(pid, "1")["winner_rel"] == "PLAN-2.md"
