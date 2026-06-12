"""Regression tests for ``forge_create_service._compensate``.

The compensation path must undo ONLY the failed create — materialization
rewrites EVERY bound asset of the kind, so a naive "unlink everything written
this run + empty the manifest bucket" wipes sibling assets' files. The fixed
compensation rolls back the DB first (binding → row) and then re-materializes
the kind, which deletes only the new asset's file and keeps siblings + the
manifest consistent.
"""

from __future__ import annotations

from app.db import (
    add_project_forge_binding,
    create_project,
    get_project,
)
from app.db.subagents import create_subagent, get_subagent
from app.services.forge_create_service import _compensate
from app.services.forge_materialization_service import materialize_primitives


def test_compensation_preserves_sibling_kind_files(isolated_db, tmp_path):
    del isolated_db
    project_id = create_project(name="comp-test", description="fixture", local_path=str(tmp_path))
    project = get_project(project_id)

    # Two pre-existing subagents, bound + materialized.
    a = create_subagent(name="sib-a", content="A body")
    b = create_subagent(name="sib-b", content="B body")
    add_project_forge_binding(project_id, "subagent", a["id"])
    add_project_forge_binding(project_id, "subagent", b["id"])
    materialize_primitives(project, ["subagent"], tmp_path)
    assert (tmp_path / ".claude" / "agents" / "sib-a.md").exists()
    assert (tmp_path / ".claude" / "agents" / "sib-b.md").exists()

    # A third create got through create+bind+materialize, then a later step
    # failed → compensation fires with every forward step completed.
    c = create_subagent(name="sib-c", content="C body")
    binding = add_project_forge_binding(project_id, "subagent", c["id"])
    materialize_primitives(project, ["subagent"], tmp_path)
    assert (tmp_path / ".claude" / "agents" / "sib-c.md").exists()

    _compensate(
        kind="subagent",
        asset_id=c["id"],
        binding_id=binding["id"],
        project=project,
        workspace_path=tmp_path,
    )

    # The failed create is fully undone…
    assert get_subagent(c["id"]) is None
    assert not (tmp_path / ".claude" / "agents" / "sib-c.md").exists()
    # …and the sibling assets' files survive.
    assert (tmp_path / ".claude" / "agents" / "sib-a.md").exists()
    assert (tmp_path / ".claude" / "agents" / "sib-b.md").exists()
