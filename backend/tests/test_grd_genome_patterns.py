"""GRD 0.4.1 pattern mining → GENOME-SUGGESTIONS (milestone sub-project #4).

The gd binary is mocked at the runner's subprocess boundary; DB exercised
against ``isolated_db``. Covers the no-flag JSON invocation, the inverted-
output gotcha (Error: prefix on exit-0 → failure), apply-flag argv, mirror on
success, promote argv, and the DB round-trip.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from app.db import get_genome_suggestions, upsert_genome_suggestions
from app.services import grd_genome_patterns_runner as runner


_PATTERNS = {
    "reflections_scanned": 12,
    "baseline_confirmed_rate": 0.5,
    "tokens_tested": 30,
    "suggestions": [
        {"token": "refactor", "n": 11, "confirmed": 9, "confirmed_rate": 0.82,
         "baseline": 0.5, "effect_size": 0.32, "raw_p": 0.01, "fdr_q": 0.04, "significant": True},
    ],
    "applied": False,
    "suggestions_path": None,
}


class _Done:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def _patch_gd(cap, done):
    """Patch the runner's gd-cmd resolution + subprocess.run to capture argv."""
    def fake_run(cmd, **kw):
        cap["cmd"] = cmd
        return done
    return (
        patch.object(runner, "_gd_cmd", side_effect=lambda extra: ["gd", *extra]),
        patch.object(runner.subprocess, "run", side_effect=fake_run),
    )


# ---- mine_patterns: no-flag JSON + mirror --------------------------------

def test_mine_patterns_no_flag_json_and_mirror(isolated_db):
    from app.db.projects import create_project

    pid = create_project("Mine")
    cap = {}
    p1, p2 = _patch_gd(cap, _Done(out=json.dumps(_PATTERNS)))
    with p1, p2:
        res = runner.mine_patterns(pid, "/cwd")
    # invoked `gd patterns` with NO --json/--raw flag (grd-tools emits JSON bare)
    assert cap["cmd"] == ["gd", "patterns"]
    assert res["success"] is True
    assert res["data"]["suggestions"][0]["token"] == "refactor"
    assert res["mirrored"] and res["mirrored"].startswith("gsug-")
    row = get_genome_suggestions(pid)
    assert row["reflections_scanned"] == 12
    assert len(row["suggestions"]) == 1


def test_mine_patterns_apply_argv(isolated_db):
    cap = {}
    p1, p2 = _patch_gd(cap, _Done(out=json.dumps({**_PATTERNS, "applied": True})))
    with p1, p2:
        runner.mine_patterns("p", "/cwd", apply=True, min_occurrences=5, effect_size=0.3, fdr_q=0.05)
    assert cap["cmd"] == [
        "gd", "patterns", "--apply", "--yes",
        "--min-occurrences", "5", "--effect-size", "0.3", "--fdr-q", "0.05",
    ]


def test_error_prefix_on_exit0_is_failure(isolated_db):
    # grd-tools prints "Error: ..." to stdout and STILL exits 0 — must fail.
    cap = {}
    p1, p2 = _patch_gd(cap, _Done(rc=0, out="Error: no GENOME-SUGGESTIONS.md found."))
    with p1, p2:
        res = runner.mine_patterns("p", "/cwd")
    assert res["success"] is False
    assert "Error:" in res["error"]
    assert res["mirrored"] is None


def test_non_json_body_is_failure(isolated_db):
    cap = {}
    p1, p2 = _patch_gd(cap, _Done(out="no significant patterns (human text)"))
    with p1, p2:
        res = runner.mine_patterns("p", "/cwd")
    assert res["success"] is False
    assert "non-JSON" in res["error"]


# ---- promote_suggestion --------------------------------------------------

def test_promote_suggestion_argv_and_parse(isolated_db):
    cap = {}
    out = json.dumps({"promoted": "refactor-rate", "heuristic": "h", "genome_path": ".planning/GENOME.md"})
    p1, p2 = _patch_gd(cap, _Done(out=out))
    with p1, p2:
        res = runner.promote_suggestion("/cwd", "refactor-rate")
    assert cap["cmd"] == ["gd", "genome", "promote-suggestion", "refactor-rate"]
    assert res["success"] is True
    assert res["data"]["promoted"] == "refactor-rate"


def test_promote_requires_slug(isolated_db):
    assert runner.promote_suggestion("/cwd", "")["success"] is False


# ---- DB round-trip -------------------------------------------------------

def test_upsert_genome_suggestions_full_replace(isolated_db):
    from app.db.projects import create_project

    pid = create_project("Sug")
    a = upsert_genome_suggestions(project_id=pid, reflections_scanned=1, applied=False)
    b = upsert_genome_suggestions(project_id=pid, reflections_scanned=2, applied=True,
                                  suggestions_json=json.dumps([{"token": "x"}]))
    assert a == b  # stable id, one row per project
    row = get_genome_suggestions(pid)
    assert row["reflections_scanned"] == 2
    assert row["applied"] is True
    assert row["suggestions"][0]["token"] == "x"
