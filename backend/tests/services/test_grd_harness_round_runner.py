"""Tests for the GRD life-harness round runner (finalize + DB mirror)."""

import json
import os

from app.db.grd_harness_rounds import get_harness_round
from app.services import grd_harness_round_runner as r


def test_finalize_round_mirrors_record_and_patch(tmp_path, isolated_db):
    from app.database import create_project as db_create_project

    pid = db_create_project(name="P")
    cwd = str(tmp_path)
    rounds = os.path.join(cwd, ".planning", "harness", "rounds", "20260614-120000")
    os.makedirs(rounds)
    with open(os.path.join(rounds, "patch.json"), "w") as f:
        json.dump({"summary": "tweak", "confidence": 0.72, "entries": []}, f)

    stdout = json.dumps({
        "round_id": "20260614-120000",
        "status": "applied",
        "detail": "ok",
        "evidence_count": 9,
        "patch_hash": "abcd",
        "eval_report": {"checks": [{"name": "tsc", "exit_code": 0}]},
        "applied_sha": "sha9",
    })

    r._finalize_round(pid, cwd, stdout, 0)

    got = get_harness_round(pid, "20260614-120000")
    assert got["status"] == "applied"
    assert got["confidence"] == 0.72
    assert got["summary"] == "tweak"
    assert got["evidence_count"] == 9
    assert got["applied_sha"] == "sha9"
    assert got["eval"]["checks"][0]["name"] == "tsc"


def test_finalize_round_records_error_on_bad_output(tmp_path, isolated_db):
    from app.database import create_project as db_create_project

    pid = db_create_project(name="P")
    r._finalize_round(pid, str(tmp_path), "not json!!!", 1)
    got = get_harness_round(pid, "error")
    assert got["status"] == "error"
