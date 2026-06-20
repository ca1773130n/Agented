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
    from app.db import project_forge_bindings as bindings_repo
    from app.db import rules as rules_repo
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
    n, failures = reverse_apply_journal("prj", journal)
    assert n == 1 and failures == []
    assert rules_repo.get_rule(int(rid))["description"] == "OLD"


def test_reverse_journal_create_deletes_and_unbinds(isolated_db):
    from app.database import get_connection
    from app.db import project_forge_bindings as bindings_repo
    from app.db import rules as rules_repo
    from app.services.harness_evolution_rollback import reverse_apply_journal

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prc', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="created", rule_type="validation", description="x", project_id="prc"
    )
    bindings_repo.add_binding("prc", "rule", str(rid))
    journal = [{"kind": "rule", "op": "create", "asset_id": str(rid), "before": None}]
    n, failures = reverse_apply_journal("prc", journal)
    assert n == 1 and failures == []
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
    n, failures = reverse_apply_journal("prd", journal)
    assert n == 1 and failures == []
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
    n, failures = reverse_apply_journal("pnone", journal)
    assert n == 2 and failures == []


def test_reverse_delete_idempotent_no_duplicate(isolated_db):
    from app.database import get_connection
    from app.db import rules as rules_repo
    from app.services.harness_evolution_rollback import reverse_apply_journal

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pid', 'P', 'active')")
        conn.commit()
    journal = [
        {
            "kind": "rule",
            "op": "delete",
            "asset_id": "1",
            "before": {
                "name": "uniq",
                "rule_type": "validation",
                "description": "d",
                "action": "a",
                "enabled": 1,
            },
        }
    ]
    reverse_apply_journal("pid", journal)
    reverse_apply_journal("pid", journal)  # retry must NOT duplicate
    matches = [r for r in rules_repo.get_rules_by_project("pid") if r["name"] == "uniq"]
    assert len(matches) == 1


def test_reverse_update_missing_before_is_failure(isolated_db):
    from app.services.harness_evolution_rollback import reverse_apply_journal

    journal = [{"kind": "rule", "op": "update", "asset_id": "5", "before": None}]
    n, failures = reverse_apply_journal("pany", journal)
    assert n == 0 and len(failures) == 1 and failures[0]["op"] == "update"


def test_revert_round_refuses_non_applied(isolated_db):
    from app.services.harness_evolution_rollback import revert_round

    rid = _applied_round("prr")
    evo.mark_reverted(rid)
    result = revert_round(rid, revert_git=False)
    assert result.status == "failed"


def test_revert_round_refuses_missing_journal(isolated_db):
    from app.services.harness_evolution_rollback import revert_round

    # _applied_round with empty journal []
    rid = _applied_round("prm", journal=[])
    result = revert_round(rid, revert_git=False)
    assert result.status == "failed"
    assert "journal" in result.error.lower()


def test_revert_round_reverts_applied(isolated_db):
    from app.database import get_connection
    from app.db import project_forge_bindings as bindings_repo
    from app.db import rules as rules_repo
    from app.services.harness_evolution_rollback import revert_round

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prv', 'P', 'active')")
        conn.commit()
    asset = rules_repo.create_rule(
        name="c", rule_type="validation", description="x", project_id="prv"
    )
    bindings_repo.add_binding("prv", "rule", str(asset))
    round_id = evo.start_round(
        project_id="prv",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/x",
    )
    evo.mark_running(round_id)
    journal = [{"kind": "rule", "op": "create", "asset_id": str(asset), "before": None}]
    evo.mark_applied(
        round_id,
        output_patch={"entries": []},
        applied_asset_ids=[{"kind": "rule", "op": "create", "asset_id": str(asset)}],
        notes="",
        git_commit_sha=None,
        apply_journal_json=json.dumps(journal),
    )
    result = revert_round(round_id, revert_git=False)
    assert result.status == "reverted"
    assert rules_repo.get_rule(int(asset)) is None
    assert evo.get_round(round_id)["status"] == "reverted"


def test_revert_round_conflict_with_later_round(isolated_db):
    from app.database import get_connection
    from app.services.harness_evolution_rollback import revert_round

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prx', 'P', 'active')")
        conn.commit()
    j = [
        {
            "kind": "rule",
            "op": "update",
            "asset_id": "7",
            "before": {
                "name": "r",
                "rule_type": "validation",
                "description": "o",
                "action": "a",
                "enabled": 1,
            },
        }
    ]
    # round A (older), round B (newer) both touch asset 7. Backdate A so B sorts later.
    a = evo.start_round(
        project_id="prx",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/t",
    )
    evo.mark_running(a)
    evo.mark_applied(
        a,
        output_patch={"entries": []},
        applied_asset_ids=[],
        notes="",
        git_commit_sha=None,
        apply_journal_json=json.dumps(j),
    )
    with get_connection() as conn:
        conn.execute(
            "UPDATE harness_evolution_rounds SET started_at='2000-01-01T00:00:00' WHERE id=?", (a,)
        )
        conn.commit()
    b = evo.start_round(
        project_id="prx",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/t",
    )
    evo.mark_running(b)
    evo.mark_applied(
        b,
        output_patch={"entries": []},
        applied_asset_ids=[],
        notes="",
        git_commit_sha=None,
        apply_journal_json=json.dumps(j),
    )
    result = revert_round(
        a, revert_git=False
    )  # reverting A: B is a later applied round touching asset 7
    assert result.status == "conflict"
    assert any(str(c.get("asset_id")) == "7" for c in result.conflicts)
    forced = revert_round(a, revert_git=False, force=True)
    assert forced.status == "reverted"


def test_set_revert_error_truncates_at_2000(isolated_db):
    rid = _applied_round("ptrunc")
    evo.set_revert_error(rid, "x" * 2500)
    row = evo.get_round(rid)
    assert len(row["revert_error"]) == 2000


def test_revert_round_retry_after_db_reversed_is_idempotent(isolated_db):
    """A round whose DB was already reversed (e.g. git failed on first attempt,
    leaving status applied) must revert cleanly on retry — the DB reversal is
    idempotent, so a second revert_round (revert_git=False) succeeds."""
    from app.database import get_connection
    from app.db import project_forge_bindings as bindings_repo
    from app.db import rules as rules_repo
    from app.services.harness_evolution_rollback import revert_round

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pretry', 'P', 'active')")
        conn.commit()
    asset = rules_repo.create_rule(
        name="c", rule_type="validation", description="x", project_id="pretry"
    )
    bindings_repo.add_binding("pretry", "rule", str(asset))
    rid = evo.start_round(
        project_id="pretry",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/t",
    )
    evo.mark_running(rid)
    journal = [{"kind": "rule", "op": "create", "asset_id": str(asset), "before": None}]
    evo.mark_applied(
        rid,
        output_patch={"entries": []},
        applied_asset_ids=[],
        notes="",
        git_commit_sha=None,
        apply_journal_json=json.dumps(journal),
    )
    # first revert (no git) succeeds
    r1 = revert_round(rid, revert_git=False)
    assert r1.status == "reverted"
    # simulate a retry scenario: force status back to applied and revert again — must not error
    with get_connection() as conn:
        conn.execute("UPDATE harness_evolution_rounds SET status='applied' WHERE id=?", (rid,))
        conn.commit()
    r2 = revert_round(rid, revert_git=False)
    assert (
        r2.status == "reverted"
    )  # idempotent: asset already gone, delete-reversal is a no-op success
    assert r2.error == ""


def test_reverse_delete_mcp_idempotent_no_duplicate(isolated_db):
    from app.database import get_connection
    from app.db import mcp_servers as mcp_repo
    from app.services.harness_evolution_rollback import reverse_apply_journal

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pmcp', 'P', 'active')")
        conn.commit()
    journal = [
        {
            "kind": "mcp_server",
            "op": "delete",
            "asset_id": "old",
            "before": {
                "name": "ctxsrv",
                "description": "d",
                "server_type": "stdio",
                "command": "ctx",
                "args": None,
                "env_json": None,
                "url": None,
            },
        }
    ]
    reverse_apply_journal("pmcp", journal)
    reverse_apply_journal("pmcp", journal)  # retry must NOT duplicate
    servers = [s for s in mcp_repo.get_all_mcp_servers() if s.get("name") == "ctxsrv"]
    assert len(servers) == 1
