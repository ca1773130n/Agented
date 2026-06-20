"""Phase 17-02 — subagent forge-primitive DB + registry tests.

Covers the DB+registry half of phase success criterion #1: subagents table
(subag- prefix), CRUD round-trip, name UNIQUE enforcement, dual kind-registry
membership, and that the legacy ``agents`` table is kept distinct.
"""

import sqlite3

import pytest

from app.db import (
    VALID_FORGE_BINDING_KINDS,
    create_subagent,
    delete_subagent,
    get_subagent,
    list_subagents,
    update_subagent,
)
from app.db.connection import get_connection
from app.db.project_forge_bindings import VALID_KINDS


def test_create_returns_subag_prefix():
    row = create_subagent(name="reviewer", content="---\nname: reviewer\n---\nbody")
    assert row["id"].startswith("subag-")
    assert row["name"] == "reviewer"
    assert row["content"] == "---\nname: reviewer\n---\nbody"


def test_crud_round_trip():
    created = create_subagent(name="planner", content="plan body", description="d")
    sid = created["id"]

    fetched = get_subagent(sid)
    assert fetched is not None and fetched["name"] == "planner"

    listed = list_subagents()
    assert any(r["id"] == sid for r in listed)

    assert update_subagent(sid, content="new body", description="updated") is True
    assert get_subagent(sid)["content"] == "new body"

    assert delete_subagent(sid) is True
    assert get_subagent(sid) is None


def test_name_unique():
    create_subagent(name="dup", content="a")
    with pytest.raises(sqlite3.IntegrityError):
        create_subagent(name="dup", content="b")


def test_subagent_in_both_kind_registries():
    assert "subagent" in VALID_KINDS
    assert "subagent" in VALID_FORGE_BINDING_KINDS


def test_legacy_agents_table_distinct():
    # Both tables exist and are independent: a subagent row never appears in
    # the legacy agents table.
    sid = create_subagent(name="distinct", content="x")["id"]
    with get_connection() as conn:
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "subagents" in tables
        assert "agents" in tables
        agent_match = conn.execute(
            "SELECT COUNT(*) AS c FROM agents WHERE id = ?", (sid,)
        ).fetchone()["c"]
    assert agent_match == 0
    assert get_subagent(sid) is not None
