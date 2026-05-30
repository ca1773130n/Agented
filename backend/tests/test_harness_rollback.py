import json

from app.database import get_connection
from app.db import harness_evolution as evo


def _applied_round(project_id="pr", journal=None, sha="sha1"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status) VALUES (?, 'P', 'active')", (project_id,)
        )
        conn.commit()
    rid = evo.start_round(
        project_id=project_id,
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/x",
    )
    evo.mark_running(rid)
    evo.mark_applied(
        rid,
        output_patch={"entries": []},
        applied_asset_ids=[{"kind": "rule", "op": "create", "asset_id": "1"}],
        notes="",
        git_commit_sha=sha,
        apply_journal_json=json.dumps(journal or []),
    )
    return rid


def test_apply_journal_persisted_and_decoded(isolated_db):
    journal = [{"kind": "rule", "op": "create", "asset_id": "1", "before": None}]
    rid = _applied_round(journal=journal)
    row = evo.get_round(rid)
    assert row["apply_journal"] == journal
    assert row["git_commit_sha"] == "sha1"


def test_mark_reverted_sets_state(isolated_db):
    rid = _applied_round("pr2")
    evo.mark_reverted(rid)
    assert evo.get_round(rid)["status"] == "reverted"


def test_set_revert_error_leaves_applied(isolated_db):
    rid = _applied_round("pr3")
    evo.set_revert_error(rid, "git revert failed")
    row = evo.get_round(rid)
    assert row["status"] == "applied"
    assert "git revert failed" in (row["revert_error"] or "")
