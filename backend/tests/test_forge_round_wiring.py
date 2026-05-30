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
