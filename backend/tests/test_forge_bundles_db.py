"""Cross-kind forge bundle DB tests (17-03) + a byte-for-byte guard that the
legacy ``skill_sets`` table DDL (migration 87) is left untouched."""

import re

import pytest

from app.db import (
    add_bundle_item,
    create_forge_bundle,
    delete_forge_bundle,
    list_forge_bundle_items,
)
from app.db.connection import get_connection


def _norm(sql: str) -> str:
    """Collapse all whitespace runs to a single space and strip — lets us
    compare SQL structurally without depending on indentation."""
    return re.sub(r"\s+", " ", sql).strip()


def test_cross_kind_bundle_round_trip(isolated_db):
    """A single bundle holds items of >=2 distinct kinds, returned ordered by
    position. This is the cross-kind grouping skill_sets cannot express."""
    bundle = create_forge_bundle("alpha-stack", description="mixed", scope="project")
    add_bundle_item(bundle["id"], "skill", "skill-aaa", position=1)
    add_bundle_item(bundle["id"], "command", "cmd-bbb", position=0)
    add_bundle_item(bundle["id"], "rule", "rule-ccc", position=2)

    items = list_forge_bundle_items(bundle["id"])
    assert [i["asset_id"] for i in items] == ["cmd-bbb", "skill-aaa", "rule-ccc"]
    assert {i["kind"] for i in items} == {"skill", "command", "rule"}
    # All belong to the one bundle.
    assert {i["bundle_id"] for i in items} == {bundle["id"]}


def test_add_bundle_item_auto_position(isolated_db):
    """position=None auto-assigns to the tail (max+1)."""
    bundle = create_forge_bundle("auto-pos")
    a = add_bundle_item(bundle["id"], "skill", "s1")
    b = add_bundle_item(bundle["id"], "command", "c1")
    assert a["position"] == 0
    assert b["position"] == 1


def test_add_bundle_item_rejects_unknown_kind(isolated_db):
    bundle = create_forge_bundle("bad-kind")
    with pytest.raises(ValueError):
        add_bundle_item(bundle["id"], "not_a_kind", "x")


def test_delete_bundle_cascades_items(isolated_db):
    """Deleting a bundle removes all its items — no orphan rows remain."""
    bundle = create_forge_bundle("doomed")
    add_bundle_item(bundle["id"], "skill", "s1")
    add_bundle_item(bundle["id"], "command", "c1")

    assert delete_forge_bundle(bundle["id"]) is True

    with get_connection() as conn:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM forge_bundle_items WHERE bundle_id = ?",
            (bundle["id"],),
        ).fetchone()[0]
    assert orphans == 0


# The exact skill_sets DDL as defined by migration 87 (v05_features.py) and
# schema/_skills.py — both are byte-identical. If this ever drifts, the
# legacy skills-only composer table has been touched, violating success
# criterion #4. House constraint: skill_sets must stay byte-for-byte unchanged.
_EXPECTED_SKILL_SETS_DDL = _norm(
    """
    CREATE TABLE skill_sets (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        skill_ids TEXT NOT NULL DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
)


def test_skill_sets_schema_unchanged(isolated_db):
    """Byte-for-byte (whitespace-normalized) guard on the legacy skill_sets
    DDL. The bundle work must not alter skill_sets in any way."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='skill_sets'"
        ).fetchone()
    assert row is not None, "skill_sets table missing"
    # sqlite stores 'CREATE TABLE IF NOT EXISTS skill_sets' minus the
    # IF NOT EXISTS clause; normalize both to compare structure.
    actual = _norm(row[0]).replace("IF NOT EXISTS ", "")
    assert actual == _EXPECTED_SKILL_SETS_DDL, actual
