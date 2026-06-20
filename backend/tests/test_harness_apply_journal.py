import json

import pytest
from pydantic import ValidationError

from app.database import get_connection
from app.db import project_forge_bindings as bindings_repo
from app.db import rules as rules_repo
from app.models.harness_evolution import ApplyJournalEntry, RevertResult
from app.services.harness_evolver import EvolutionPatch, PatchEntry, apply_patch


def test_apply_journal_entry_create():
    e = ApplyJournalEntry(kind="rule", op="create", asset_id="5", before=None)
    assert e.op == "create" and e.before is None


def test_apply_journal_entry_update_carries_before():
    e = ApplyJournalEntry(
        kind="rule", op="update", asset_id="5", before={"name": "r", "action": "old"}
    )
    assert e.before["action"] == "old"


def test_apply_journal_entry_rejects_bad_op():
    with pytest.raises(ValidationError):
        ApplyJournalEntry(kind="rule", op="frobnicate", asset_id="5")


def test_revert_result_shape():
    r = RevertResult(status="reverted", reversed_count=3, git_reverted=True)
    assert r.status == "reverted"
    assert r.reversed_count == 3
    assert RevertResult.model_validate_json(r.model_dump_json()).git_reverted is True


# --------------------------------------------------------------------------
# apply_patch — journal capture integration tests
# --------------------------------------------------------------------------


def _seed_project(project_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, status) VALUES (?, ?, 'active')",
            (project_id, project_id),
        )
        conn.commit()


def test_apply_patch_returns_applied_and_journal_with_update_before(isolated_db):
    _seed_project("pj-upd")
    rid = rules_repo.create_rule(
        name="r",
        rule_type="validation",
        description="OLD",
        action="old-action",
        project_id="pj-upd",
    )
    bindings_repo.add_binding("pj-upd", "rule", str(rid))
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="update",
                kind="rule",
                name="r",
                existing_asset_id=rid,
                payload={"description": "NEW", "action": "new-action"},
            )
        ]
    )
    result = apply_patch(patch, "pj-upd")
    assert isinstance(result, tuple) and len(result) == 2
    applied, journal = result
    upd = [j for j in journal if j["op"] == "update"][0]
    assert upd["before"]["description"] == "OLD"
    assert upd["before"]["action"] == "old-action"
    assert rules_repo.get_rule(int(rid))["description"] == "NEW"


def test_apply_patch_create_journal_has_no_before(isolated_db):
    _seed_project("pj-cr")
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="create",
                kind="rule",
                name="new-rule",
                existing_asset_id=None,
                payload={"rule_type": "validation", "description": "d"},
            )
        ]
    )
    applied, journal = apply_patch(patch, "pj-cr")
    cr = [j for j in journal if j["op"] == "create"][0]
    assert cr["before"] is None
    assert cr["asset_id"]


def test_apply_patch_delete_journal_captures_before(isolated_db):
    _seed_project("pj-del")
    rid = rules_repo.create_rule(
        name="todel",
        rule_type="validation",
        description="will-be-gone",
        project_id="pj-del",
    )
    bindings_repo.add_binding("pj-del", "rule", str(rid))
    patch = EvolutionPatch(
        entries=[PatchEntry(op="delete", kind="rule", name="todel", existing_asset_id=rid)]
    )
    applied, journal = apply_patch(patch, "pj-del")
    dl = [j for j in journal if j["op"] == "delete"][0]
    assert dl["before"]["description"] == "will-be-gone"
    assert rules_repo.get_rule(int(rid)) is None


def test_apply_patch_journal_is_json_serializable(isolated_db):
    _seed_project("pj-ser")
    rid = rules_repo.create_rule(name="s", project_id="pj-ser")
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="update",
                kind="rule",
                name="s",
                existing_asset_id=rid,
                payload={"description": "x"},
            )
        ]
    )
    _applied, journal = apply_patch(patch, "pj-ser")
    # Must not raise
    serialized = json.dumps(journal, default=str)
    parsed = json.loads(serialized)
    assert parsed[0]["op"] == "update"


def test_asset_to_payload_includes_none_for_restore_fidelity():
    from app.services.harness_evolver import _asset_to_payload

    before = {
        "rule_type": "validation",
        "description": "d",
        "condition": None,
        "action": "a",
        "enabled": 1,
    }
    payload = _asset_to_payload("rule", before)
    # condition=None must be PRESENT (so a restore re-clears it), not dropped
    assert "condition" in payload
    assert payload["condition"] is None


def test_skill_before_image_carries_body(isolated_db, tmp_path):
    from app.db import skills as skills_repo
    from app.services.harness_evolver import _fetch_primitive

    skill_dir = tmp_path / ".claude" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\n---\nthe body\n")
    sid = skills_repo.add_user_skill(
        skill_name="demo", skill_path=str(skill_dir / "SKILL.md"), description="d"
    )
    asset = _fetch_primitive("skill", sid)
    assert asset is not None
    assert "the body" in (asset.get("content") or "")
