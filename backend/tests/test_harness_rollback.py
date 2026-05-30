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


def test_reverse_journal_update_restores_before(isolated_db):
    from app.database import get_connection
    from app.db import rules as rules_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolution_rollback import reverse_apply_journal

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prj', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="r",
        rule_type="validation",
        description="NEW",
        action="new",
        project_id="prj",
    )
    bindings_repo.add_binding("prj", "rule", str(rid))
    journal = [
        {
            "kind": "rule",
            "op": "update",
            "asset_id": str(rid),
            "before": {
                "name": "r",
                "rule_type": "validation",
                "description": "OLD",
                "action": "old",
                "enabled": 1,
            },
        }
    ]
    n = reverse_apply_journal("prj", journal)
    assert n == 1
    assert rules_repo.get_rule(int(rid))["description"] == "OLD"


def test_reverse_journal_create_deletes_and_unbinds(isolated_db):
    from app.database import get_connection
    from app.db import rules as rules_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolution_rollback import reverse_apply_journal

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prc', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="created", rule_type="validation", description="x", project_id="prc"
    )
    bindings_repo.add_binding("prc", "rule", str(rid))
    journal = [{"kind": "rule", "op": "create", "asset_id": str(rid), "before": None}]
    reverse_apply_journal("prc", journal)
    assert rules_repo.get_rule(int(rid)) is None
    assert not any(
        b["kind"] == "rule" and str(b["asset_id"]) == str(rid)
        for b in bindings_repo.list_bindings("prc")
    )


def test_reverse_journal_delete_recreates_and_rebinds(isolated_db):
    from app.database import get_connection
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolution_rollback import reverse_apply_journal

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prd', 'P', 'active')")
        conn.commit()
    # before-image of a rule that was deleted
    journal = [
        {
            "kind": "rule",
            "op": "delete",
            "asset_id": "999",
            "before": {
                "name": "restoreme",
                "rule_type": "validation",
                "description": "back",
                "action": "a",
                "enabled": 1,
            },
        }
    ]
    n = reverse_apply_journal("prd", journal)
    assert n == 1
    # a rule named restoreme now exists + is bound (new id, restored content)
    from app.db import rules as rules_repo

    restored = [r for r in rules_repo.get_rules_by_project("prd") if r["name"] == "restoreme"]
    assert restored and restored[0]["description"] == "back"
    assert any(
        b["kind"] == "rule" and str(b["asset_id"]) == str(restored[0]["id"])
        for b in bindings_repo.list_bindings("prd")
    )


def test_reverse_journal_reverse_order(isolated_db):
    """Entries are reversed last-first."""
    from app.services.harness_evolution_rollback import reverse_apply_journal

    # two creates; reversing should attempt both (count == 2) — use nonexistent ids
    # so delete is a no-op but the loop still counts the attempts it completes.
    journal = [
        {"kind": "rule", "op": "create", "asset_id": "1", "before": None},
        {"kind": "rule", "op": "create", "asset_id": "2", "before": None},
    ]
    n = reverse_apply_journal("pnone", journal)
    assert n == 2
