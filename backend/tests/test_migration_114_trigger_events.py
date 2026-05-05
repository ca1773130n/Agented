"""v0.7.1: trigger_events migration shape + idempotence tests."""

from app.database import get_connection


def test_table_exists_with_required_columns(isolated_db):
    with get_connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(trigger_events)")}
    expected = {
        "id",
        "trigger_id",
        "received_at",
        "payload",
        "signature_header",
        "matched",
        "dispatch_status",
        "dispatch_error",
    }
    assert expected.issubset(cols)


def test_indices_exist(isolated_db):
    with get_connection() as conn:
        idx = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='trigger_events'"
            )
        }
    assert "idx_trigger_events_trigger_id" in idx
    assert "idx_trigger_events_received_at" in idx


def test_migration_is_idempotent(isolated_db):
    """Running again must not fail."""
    from app.db.migrations import _migrate_114_trigger_events

    with get_connection() as conn:
        _migrate_114_trigger_events(conn)  # second run
    with get_connection() as conn:
        rows = list(conn.execute("SELECT COUNT(*) AS c FROM trigger_events"))
        assert rows[0]["c"] == 0
