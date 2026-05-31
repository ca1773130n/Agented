"""Phase E2 Task 1: harness_kg_signals table + repo tests."""

from app.database import get_connection
from app.db import harness_kg_signals as repo


def test_record_signal_first_insert(isolated_db):
    row = repo.record_signal(
        signal_id="sig-1",
        project_id="proj-a",
        question="what about X?",
        content="guidance about X",
        weight=0.5,
        already_forged=False,
        now="2026-05-31T00:00:00Z",
        round_id="rnd-1",
    )
    assert row["signal_id"] == "sig-1"
    assert row["project_id"] == "proj-a"
    assert row["question"] == "what about X?"
    assert row["content"] == "guidance about X"
    assert row["weight"] == 0.5
    assert row["already_forged"] == 0
    assert row["first_seen_at"] == "2026-05-31T00:00:00Z"
    assert row["captured_at"] == "2026-05-31T00:00:00Z"
    assert row["round_id"] == "rnd-1"

    # re-SELECT matches
    fetched = repo.get_signal("sig-1")
    assert fetched == row


def test_record_signal_upsert_preserves_first_seen(isolated_db):
    repo.record_signal(
        signal_id="sig-2",
        project_id="proj-a",
        question="q",
        content="v1",
        weight=0.4,
        already_forged=False,
        now="2026-05-31T00:00:00Z",
    )
    updated = repo.record_signal(
        signal_id="sig-2",
        project_id="proj-a",
        question="q",
        content="v2",
        weight=0.6,
        already_forged=True,
        now="2026-06-01T12:00:00Z",
        round_id="rnd-9",
    )
    # first_seen_at PRESERVED
    assert updated["first_seen_at"] == "2026-05-31T00:00:00Z"
    # captured_at + weight + already_forged + content REFRESHED
    assert updated["captured_at"] == "2026-06-01T12:00:00Z"
    assert updated["weight"] == 0.6
    assert updated["already_forged"] == 1
    assert updated["content"] == "v2"
    assert updated["round_id"] == "rnd-9"

    assert repo.first_seen_at_for("sig-2") == "2026-05-31T00:00:00Z"


def test_list_signals_ordering_and_scoping(isolated_db):
    repo.record_signal(
        signal_id="sig-old",
        project_id="proj-a",
        question="q",
        content="old",
        weight=0.5,
        already_forged=False,
        now="2026-05-01T00:00:00Z",
    )
    repo.record_signal(
        signal_id="sig-new",
        project_id="proj-a",
        question="q",
        content="new",
        weight=0.5,
        already_forged=False,
        now="2026-05-31T00:00:00Z",
    )
    repo.record_signal(
        signal_id="sig-other",
        project_id="proj-b",
        question="q",
        content="other-project",
        weight=0.5,
        already_forged=False,
        now="2026-05-15T00:00:00Z",
    )
    rows = repo.list_signals("proj-a")
    ids = [r["signal_id"] for r in rows]
    assert ids == ["sig-new", "sig-old"]  # newest captured_at first
    assert "sig-other" not in ids  # project scoped

    rows_b = repo.list_signals("proj-b")
    assert [r["signal_id"] for r in rows_b] == ["sig-other"]


def test_ensure_tables_idempotent(isolated_db):
    with get_connection() as conn:
        repo._ensure_kg_signal_tables(conn)
        repo._ensure_kg_signal_tables(conn)  # second call, no error
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_kg_signals)")}
    assert "signal_id" in cols
    assert "first_seen_at" in cols


def test_get_signal_and_first_seen_unknown(isolated_db):
    assert repo.get_signal("nope") is None
    assert repo.first_seen_at_for("nope") is None


def test_migration_142_creates_table(isolated_db):
    """The v07 migration body creates the table + index on a bare conn."""
    from app.db.migrations.v07_features import _migrate_142_harness_kg_signals

    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS harness_kg_signals")
        _migrate_142_harness_kg_signals(conn)
        _migrate_142_harness_kg_signals(conn)  # idempotent
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_kg_signals)")}
        idx = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='harness_kg_signals'"
            )
        }
    expected = {
        "signal_id",
        "project_id",
        "round_id",
        "question",
        "content",
        "weight",
        "already_forged",
        "first_seen_at",
        "captured_at",
    }
    assert expected.issubset(cols)
    assert "idx_hks_project" in idx
