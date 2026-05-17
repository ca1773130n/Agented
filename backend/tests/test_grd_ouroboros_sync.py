"""Tests for the v0.7.85 GRD Ouroboros artifact mirror.

Covers:
  * Migration v127 created the new tables + project_plans columns.
  * ``grd_ouroboros`` CRUD helpers (upsert reflection, dead-ends
    wipe-and-reload, genome snapshots monotonic sequence).
  * ``GrdSyncService`` parsers for VERIFICATION.md ``## Reflection``
    sections, DEAD-ENDS.md yaml blocks, and GENOME.md snapshots.
"""

from __future__ import annotations

from pathlib import Path

from app.db.connection import get_connection
from app.db.grd_ouroboros import (
    add_dead_end,
    add_genome_snapshot,
    count_reflections_by_verdict,
    delete_dead_ends_for_project,
    get_latest_genome_snapshot,
    get_phase_reflections,
    list_dead_ends,
    list_genome_snapshots,
    max_genome_sequence,
    update_plan_ouroboros_fields,
    upsert_phase_reflection,
)
from app.services.grd_sync_service import GrdSyncService


# ---------------------------------------------------------------------
# Migration v127
# ---------------------------------------------------------------------


def test_migration_127_created_tables_and_columns(isolated_db):
    del isolated_db
    with get_connection() as conn:
        # New tables present
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for t in (
            "phase_reflections",
            "project_dead_ends",
            "project_genome_snapshots",
        ):
            assert t in tables, f"migration 127 must create {t}"
        # project_plans gained the v0.3.24 frontmatter columns.
        plan_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(project_plans)").fetchall()
        }
        for col in ("hypothesis", "predicted_outcome", "verdict"):
            assert col in plan_cols, f"migration 127 must add project_plans.{col}"


# ---------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------


def _seed_phase(conn) -> str:
    """Insert a minimal phase row + parent milestone + project so FK
    constraints don't fail in tests. Returns the phase id.
    """
    from app.db.ids import (
        _get_unique_milestone_id,
        _get_unique_phase_id,
        _get_unique_project_id,
    )

    pid = _get_unique_project_id(conn)
    conn.execute(
        "INSERT INTO projects (id, name, local_path) VALUES (?, ?, ?)",
        (pid, "test-project", "/tmp/test-project"),
    )
    mid = _get_unique_milestone_id(conn)
    conn.execute(
        "INSERT INTO milestones (id, project_id, version, title) VALUES (?, ?, ?, ?)",
        (mid, pid, "v0.0.1", "Test Milestone"),
    )
    phid = _get_unique_phase_id(conn)
    conn.execute(
        "INSERT INTO project_phases (id, milestone_id, phase_number, name) VALUES (?, ?, ?, ?)",
        (phid, mid, 1, "Test Phase"),
    )
    conn.commit()
    return phid


def test_upsert_phase_reflection_inserts_and_updates(isolated_db):
    del isolated_db
    with get_connection() as conn:
        phase_id = _seed_phase(conn)
    rid = upsert_phase_reflection(
        phase_id=phase_id,
        hypothesis="X will work",
        predicted_outcome="Y",
        verdict="confirmed",
        source_path="/proj/.planning/phases/1-x/01-VERIFICATION.md",
        content_hash="hash-v1",
    )
    assert rid
    rows = get_phase_reflections(phase_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "confirmed"

    # Same source_path → update in place, not duplicate.
    rid2 = upsert_phase_reflection(
        phase_id=phase_id,
        hypothesis="X will work (revised)",
        predicted_outcome="Y",
        verdict="partial",
        source_path="/proj/.planning/phases/1-x/01-VERIFICATION.md",
        content_hash="hash-v2",
    )
    assert rid2 == rid
    rows = get_phase_reflections(phase_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "partial"
    assert rows[0]["hypothesis"].endswith("(revised)")


def test_count_reflections_by_verdict(isolated_db):
    del isolated_db
    with get_connection() as conn:
        phase_id = _seed_phase(conn)
        # Reverse-lookup the project_id via the phase → milestone chain.
        row = conn.execute(
            """
            SELECT m.project_id
            FROM project_phases pp
            JOIN milestones m ON m.id = pp.milestone_id
            WHERE pp.id = ?
            """,
            (phase_id,),
        ).fetchone()
        project_id = row[0]
    upsert_phase_reflection(phase_id=phase_id, hypothesis="a", verdict="confirmed", source_path="a")
    upsert_phase_reflection(phase_id=phase_id, hypothesis="b", verdict="falsified", source_path="b")
    upsert_phase_reflection(phase_id=phase_id, hypothesis="c", verdict="falsified", source_path="c")
    counts = count_reflections_by_verdict(project_id)
    assert counts["confirmed"] == 1
    assert counts["falsified"] == 2


def test_dead_ends_wipe_and_reload(isolated_db):
    del isolated_db
    with get_connection() as conn:
        from app.db.ids import _get_unique_project_id

        pid = _get_unique_project_id(conn)
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?, ?, ?)",
            (pid, "test", "/tmp/test"),
        )
        conn.commit()
    add_dead_end(project_id=pid, approach="A", reason="fail")
    add_dead_end(project_id=pid, approach="B", reason="fail")
    assert len(list_dead_ends(pid)) == 2

    removed = delete_dead_ends_for_project(pid)
    assert removed == 2
    assert list_dead_ends(pid) == []


def test_genome_snapshots_monotonic_sequence(isolated_db):
    del isolated_db
    with get_connection() as conn:
        from app.db.ids import _get_unique_project_id

        pid = _get_unique_project_id(conn)
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?, ?, ?)",
            (pid, "test", "/tmp/test"),
        )
        conn.commit()
    assert max_genome_sequence(pid) == 0
    add_genome_snapshot(project_id=pid, sequence_number=1, content="first")
    add_genome_snapshot(project_id=pid, sequence_number=2, content="second")
    assert max_genome_sequence(pid) == 2
    latest = get_latest_genome_snapshot(pid)
    assert latest["sequence_number"] == 2
    assert latest["content"] == "second"
    snapshots = list_genome_snapshots(pid)
    assert [s["sequence_number"] for s in snapshots] == [2, 1]


def test_update_plan_ouroboros_fields_partial(isolated_db):
    del isolated_db
    with get_connection() as conn:
        phase_id = _seed_phase(conn)
        from app.db.ids import _get_unique_plan_id

        plan_id = _get_unique_plan_id(conn)
        conn.execute(
            "INSERT INTO project_plans (id, phase_id, plan_number, title) VALUES (?, ?, ?, ?)",
            (plan_id, phase_id, 1, "p"),
        )
        conn.commit()
    # Hypothesis only
    ok = update_plan_ouroboros_fields(plan_id, hypothesis="hy")
    assert ok is True
    # Verdict only — predicted_outcome stays None
    ok = update_plan_ouroboros_fields(plan_id, verdict="confirmed")
    assert ok is True
    with get_connection() as conn:
        row = conn.execute(
            "SELECT hypothesis, predicted_outcome, verdict FROM project_plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
    assert row[0] == "hy"
    assert row[1] is None
    assert row[2] == "confirmed"

    # No fields → no write.
    assert update_plan_ouroboros_fields(plan_id) is False


# ---------------------------------------------------------------------
# Sync parsers
# ---------------------------------------------------------------------


def test_sync_dead_ends_parses_yaml_blocks(isolated_db, tmp_path):
    del isolated_db
    with get_connection() as conn:
        from app.db.ids import _get_unique_project_id

        pid = _get_unique_project_id(conn)
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?, ?, ?)",
            (pid, "test", str(tmp_path)),
        )
        conn.commit()
    dead_ends = tmp_path / "DEAD-ENDS.md"
    dead_ends.write_text(
        """# Dead Ends Registry

## try-x-approach

```yaml
approach: "Tried X via lib Y"
slug: try-x-approach
tried_in_phases: [42]
verdict: falsified
evidence:
  - "lib Y leaks memory at scale"
status: active
notes: "use Z instead"
```

## another-failed

```yaml
approach: "Caching everything"
slug: another-failed
tried_in_phases: [43, 44]
verdict: falsified
status: active
```
""",
        encoding="utf-8",
    )
    results = {"synced": 0, "skipped": 0, "errors": []}
    GrdSyncService._sync_dead_ends(pid, dead_ends, results)
    rows = list_dead_ends(pid)
    assert len(rows) == 2
    approaches = {r["approach"] for r in rows}
    assert "Tried X via lib Y" in approaches
    assert "Caching everything" in approaches


def test_sync_dead_ends_idempotent_on_unchanged_file(isolated_db, tmp_path):
    del isolated_db
    with get_connection() as conn:
        from app.db.ids import _get_unique_project_id

        pid = _get_unique_project_id(conn)
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?, ?, ?)",
            (pid, "test", str(tmp_path)),
        )
        conn.commit()
    dead_ends = tmp_path / "DEAD-ENDS.md"
    dead_ends.write_text(
        """# Dead Ends Registry

## x

```yaml
approach: "x"
slug: x
tried_in_phases: []
verdict: falsified
status: active
```
""",
        encoding="utf-8",
    )
    results = {"synced": 0, "skipped": 0, "errors": []}
    GrdSyncService._sync_dead_ends(pid, dead_ends, results)
    assert results["synced"] == 1
    # Re-run — should now skip (hash matches).
    GrdSyncService._sync_dead_ends(pid, dead_ends, results)
    assert results["skipped"] == 1


def test_sync_genome_appends_snapshot_with_incrementing_sequence(isolated_db, tmp_path):
    del isolated_db
    with get_connection() as conn:
        from app.db.ids import _get_unique_project_id

        pid = _get_unique_project_id(conn)
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?, ?, ?)",
            (pid, "test", str(tmp_path)),
        )
        conn.commit()
    genome = tmp_path / "GENOME.md"
    genome.write_text("# GENOME\n\nFirst state", encoding="utf-8")
    results = {"synced": 0, "skipped": 0, "errors": []}
    GrdSyncService._sync_genome(pid, genome, results)
    assert max_genome_sequence(pid) == 1

    # Same content → skipped, no new snapshot.
    GrdSyncService._sync_genome(pid, genome, results)
    assert max_genome_sequence(pid) == 1
    assert results["skipped"] == 1

    # Content change → new snapshot at seq 2.
    genome.write_text("# GENOME\n\nSecond state", encoding="utf-8")
    GrdSyncService._sync_genome(pid, genome, results)
    assert max_genome_sequence(pid) == 2
    latest = get_latest_genome_snapshot(pid)
    assert latest["content"].endswith("Second state")


def test_sync_phase_reflection_parses_verification_table(isolated_db, tmp_path):
    del isolated_db
    with get_connection() as conn:
        phase_id = _seed_phase(conn)
        from app.db.ids import _get_unique_project_id

        # Re-resolve project_id via phase's milestone.
        row = conn.execute(
            "SELECT m.project_id FROM project_phases pp "
            "JOIN milestones m ON m.id = pp.milestone_id WHERE pp.id = ?",
            (phase_id,),
        ).fetchone()
        pid = row[0]
    verification = tmp_path / "01-VERIFICATION.md"
    verification.write_text(
        """# Verification

## Reflection

| Field | Value |
| --- | --- |
| hypothesis | adding feature X will reduce drift |
| predicted_outcome | drift score < 0.5 |
| actual_outcome | drift score = 0.42 |
| verdict | confirmed |
| evidence | gd health --json; logs/run-42.txt |
""",
        encoding="utf-8",
    )
    results = {"synced": 0, "skipped": 0, "errors": []}
    GrdSyncService._sync_phase_reflection(pid, verification, phase_id, results)
    rows = get_phase_reflections(phase_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "confirmed"
    assert rows[0]["hypothesis"].startswith("adding feature X")
    assert "drift score = 0.42" in (rows[0]["actual_outcome"] or "")


def test_sync_phase_reflection_skips_when_section_missing(isolated_db, tmp_path):
    del isolated_db
    with get_connection() as conn:
        phase_id = _seed_phase(conn)
        row = conn.execute(
            "SELECT m.project_id FROM project_phases pp "
            "JOIN milestones m ON m.id = pp.milestone_id WHERE pp.id = ?",
            (phase_id,),
        ).fetchone()
        pid = row[0]
    verification = tmp_path / "01-VERIFICATION.md"
    verification.write_text("# Verification\n\nNo reflection section.\n", encoding="utf-8")
    results = {"synced": 0, "skipped": 0, "errors": []}
    GrdSyncService._sync_phase_reflection(pid, verification, phase_id, results)
    # Quiet no-op — no row created, no error.
    assert get_phase_reflections(phase_id) == []
    assert results["errors"] == []
