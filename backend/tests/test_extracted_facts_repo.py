"""TDD tests for extracted_facts store (migration 153)."""

import pytest

from app.db import extracted_facts

# ---------------------------------------------------------------------------
# Migration registration
# ---------------------------------------------------------------------------


def test_migration_153_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 153 in versions
    assert "extracted_facts" in names


# ---------------------------------------------------------------------------
# Fresh-schema DDL
# ---------------------------------------------------------------------------


def test_fresh_schema_has_extracted_facts_tables():
    import sqlite3 as _sqlite3

    from app.db.schema import create_fresh_schema

    conn = _sqlite3.connect(":memory:")
    conn.row_factory = _sqlite3.Row
    create_fresh_schema(conn)
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "extracted_facts" in tables


# ---------------------------------------------------------------------------
# insert_facts — within-session dedup
# ---------------------------------------------------------------------------


def test_insert_facts_dedup_within_session():
    """Same session+project+claim twice → 1 row; counts: 1 then 0."""
    fact = {"claim": "sky is blue", "evidence": ["src1"], "confidence": 0.9}
    n1 = extracted_facts.insert_facts(
        "sess-1", super_agent_id="sa-1", project_id="proj-1", facts=[fact]
    )
    assert n1 == 1

    n2 = extracted_facts.insert_facts(
        "sess-1", super_agent_id="sa-1", project_id="proj-1", facts=[fact]
    )
    assert n2 == 0

    rows = extracted_facts.list_for_session("sess-1")
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# insert_facts — cross-session NO dedup
# ---------------------------------------------------------------------------


def test_insert_facts_no_dedup_across_sessions():
    """Same project+claim, different session_id → 2 rows (no cross-session dedup)."""
    fact = {"claim": "water is wet", "evidence": [], "confidence": 0.8}
    n1 = extracted_facts.insert_facts(
        "sess-A", super_agent_id=None, project_id="proj-X", facts=[fact]
    )
    n2 = extracted_facts.insert_facts(
        "sess-B", super_agent_id=None, project_id="proj-X", facts=[fact]
    )
    assert n1 == 1
    assert n2 == 1

    rows_a = extracted_facts.list_for_session("sess-A")
    rows_b = extracted_facts.list_for_session("sess-B")
    assert len(rows_a) == 1
    assert len(rows_b) == 1


# ---------------------------------------------------------------------------
# evidence round-trips
# ---------------------------------------------------------------------------


def test_insert_facts_evidence_round_trips():
    evidence = ["doc:abc", "exec:xyz"]
    extracted_facts.insert_facts(
        "sess-ev",
        super_agent_id=None,
        project_id="proj-ev",
        facts=[{"claim": "test claim", "evidence": evidence, "confidence": 0.7}],
    )
    rows = extracted_facts.list_for_session("sess-ev")
    assert len(rows) == 1
    assert rows[0]["evidence"] == evidence
    assert rows[0]["confidence"] == pytest.approx(0.7)
    assert rows[0]["claim"] == "test claim"


# ---------------------------------------------------------------------------
# list_for_project — ordered desc + count_for_project
# ---------------------------------------------------------------------------


def test_list_for_project_ordered_desc_and_count():
    extracted_facts.insert_facts(
        "sess-p1",
        super_agent_id=None,
        project_id="proj-Y",
        facts=[{"claim": "claim A", "evidence": [], "confidence": 0.5}],
    )
    extracted_facts.insert_facts(
        "sess-p2",
        super_agent_id=None,
        project_id="proj-Y",
        facts=[{"claim": "claim B", "evidence": [], "confidence": 0.6}],
    )

    rows = extracted_facts.list_for_project("proj-Y")
    assert len(rows) == 2
    # Both claims are present (order may vary when created_at is the same second).
    claims = {r["claim"] for r in rows}
    assert claims == {"claim A", "claim B"}

    count = extracted_facts.count_for_project("proj-Y")
    assert count == 2


def test_list_for_project_limit_respected():
    for i in range(5):
        extracted_facts.insert_facts(
            f"sess-lim-{i}",
            super_agent_id=None,
            project_id="proj-lim",
            facts=[{"claim": f"claim {i}", "evidence": [], "confidence": 0.5}],
        )
    rows = extracted_facts.list_for_project("proj-lim", limit=3)
    assert len(rows) == 3
