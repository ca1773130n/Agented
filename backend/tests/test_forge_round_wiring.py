"""run_evolution_round materializes + commits on apply and records metadata."""

from __future__ import annotations

from app.database import get_connection
from app.db import harness_evolution as evo_repo


def test_mark_applied_persists_materialization_metadata(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('p', 'P', 'active')")
        conn.commit()
    rid = evo_repo.start_round(
        project_id="p",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/x",
    )
    evo_repo.mark_applied(
        rid,
        output_patch={"entries": []},
        applied_asset_ids=[],
        notes="",
        materialization_result_json='{"written": []}',
        git_commit_sha="abc123",
    )
    row = evo_repo.get_round(rid)
    assert row["git_commit_sha"] == "abc123"
    assert row["materialization_result_json"] == '{"written": []}'


def test_skill_recorded_in_materialization(isolated_db, tmp_path):
    from app.db import project_forge_bindings as bindings_repo
    from app.db import skills as skills_repo
    from app.services.forge_materialization_service import materialize_primitives

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status, local_path) VALUES ('ps', 'P', 'active', ?)",
            (str(tmp_path),),
        )
        conn.commit()
    # simulate a skill already on disk + in DB (as the evolver would have created)
    skill_dir = tmp_path / ".claude" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\n---\nbody\n")
    sid = skills_repo.add_user_skill(
        skill_name="demo",
        skill_path=str(skill_dir / "SKILL.md"),
        description="d",
    )
    bindings_repo.add_binding("ps", "skill", str(sid))
    result = materialize_primitives({"id": "ps"}, ["skill"], tmp_path)
    assert ".claude/skills/demo/SKILL.md" in {w.rel_path for w in result.written}


def test_skill_unbind_records_deletion_for_staging(isolated_db, tmp_path):
    """When a skill is unbound, the next materialize records its prior SKILL.md
    in result.deleted so the forge commit can stage the removal — even though
    the file was already unlinked at apply time."""
    from app.db import project_forge_bindings as bindings_repo
    from app.db import skills as skills_repo
    from app.services.forge_materialization_service import materialize_primitives

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status, local_path) VALUES ('pd', 'P', 'active', ?)",
            (str(tmp_path),),
        )
        conn.commit()
    skill_dir = tmp_path / ".claude" / "skills" / "gone"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: gone\n---\nx\n")
    sid = skills_repo.add_user_skill(
        skill_name="gone", skill_path=str(skill_dir / "SKILL.md"), description="d"
    )
    bindings_repo.add_binding("pd", "skill", str(sid))
    # first materialize records the skill + writes the manifest skill bucket
    materialize_primitives({"id": "pd"}, ["skill"], tmp_path)
    # simulate _delete_skill: unbind + remove file from disk
    for row in bindings_repo.list_bindings("pd"):
        if row["kind"] == "skill":
            bindings_repo.remove_binding(row["id"])
    (skill_dir / "SKILL.md").unlink()
    # second materialize: prior skill is stale → recorded in result.deleted
    result = materialize_primitives({"id": "pd"}, ["skill"], tmp_path)
    assert ".claude/skills/gone/SKILL.md" in result.deleted


def test_apply_patch_delete_removes_binding(isolated_db):
    """apply_patch with op=delete must remove the project→asset binding."""
    from app.db import commands as commands_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolver import EvolutionPatch, PatchEntry, apply_patch

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pdel', 'P', 'active')")
        conn.commit()

    cid = commands_repo.create_command(name="bye", description="d", content="x", project_id="pdel")
    assert cid is not None
    bindings_repo.add_binding("pdel", "command", str(cid))
    assert any(
        b["kind"] == "command" and str(b["asset_id"]) == str(cid)
        for b in bindings_repo.list_bindings("pdel")
    )

    patch = EvolutionPatch(
        entries=[
            PatchEntry(op="delete", kind="command", name="bye", existing_asset_id=cid, payload={})
        ],
        notes="",
    )
    apply_patch(patch, "pdel")

    assert not any(
        b["kind"] == "command" and str(b["asset_id"]) == str(cid)
        for b in bindings_repo.list_bindings("pdel")
    )
