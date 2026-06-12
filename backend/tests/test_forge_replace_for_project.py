"""Regression tests for the provenance-dropping bug in
``project_forge_bindings.replace_for_project``.

Bug (17-RESEARCH §17-01): ``replace_for_project`` deletes all bindings for a
project then re-INSERTs with a 6-column list, silently dropping
``source_scope``/``source_shared_binding_id``/``fingerprint`` and never setting
``conflict_policy`` (which falls to its column DEFAULT ``'local_wins'``). A
PUT-style replace therefore degrades shared/propagated bindings to
project-local provenance.
"""

from __future__ import annotations

from app.db.connection import get_connection
from app.db.project_forge_bindings import (
    _ensure_propagation_columns,
    replace_for_project,
)


def _seed_project(project_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status) VALUES (?, 'P', 'active')",
            (project_id,),
        )
        conn.commit()


def _read_provenance(project_id: str) -> dict:
    """Read provenance columns straight from the row, avoiding any helper
    that might re-coalesce values."""
    with get_connection() as conn:
        _ensure_propagation_columns(conn)
        row = conn.execute(
            "SELECT source_scope, source_shared_binding_id, fingerprint, "
            "conflict_policy FROM project_forge_bindings WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    assert row is not None, "expected exactly one binding row to exist"
    return {
        "source_scope": row["source_scope"],
        "source_shared_binding_id": row["source_shared_binding_id"],
        "fingerprint": row["fingerprint"],
        "conflict_policy": row["conflict_policy"],
    }


def test_replace_for_project_preserves_provenance(isolated_db):
    project_id = "proj-prov01"
    _seed_project(project_id)
    incoming = {
        "kind": "rule",
        "asset_id": "42",
        "role": "default",
        "enabled": True,
        "source_scope": "shared",
        "source_shared_binding_id": 777,
        "fingerprint": "fp-deadbeef",
        "conflict_policy": "shared_wins",
    }

    replace_for_project(project_id, [incoming])

    got = _read_provenance(project_id)
    assert got["source_scope"] == "shared"
    assert got["source_shared_binding_id"] == 777
    assert got["fingerprint"] == "fp-deadbeef"
    assert got["conflict_policy"] == "shared_wins"


def test_replace_for_project_defaults_match_add_binding(isolated_db):
    project_id = "proj-prov02"
    _seed_project(project_id)
    incoming = {
        "kind": "command",
        "asset_id": "abc",
        "role": None,
        "enabled": True,
    }

    replace_for_project(project_id, [incoming])

    got = _read_provenance(project_id)
    assert got["source_scope"] == "project"
    assert got["source_shared_binding_id"] is None
    assert got["fingerprint"] is None
    assert got["conflict_policy"] == "local_wins"
