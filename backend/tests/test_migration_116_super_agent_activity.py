"""v0.7.7: super_agent_activity migration shape + idempotence tests."""

from app.database import get_connection


def test_table_exists(isolated_db):
    with get_connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(super_agent_activity)")}
    expected = {
        "id",
        "super_agent_id",
        "session_id",
        "event_type",
        "recorded_at",
        "payload",
        "cost_tokens_in",
        "cost_tokens_out",
        "cost_usd",
        "status",
        "error_message",
        "duration_ms",
    }
    assert expected.issubset(cols)


def test_indices_exist(isolated_db):
    with get_connection() as conn:
        idx = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='super_agent_activity'"
            )
        }
    assert "idx_saa_super_agent_recorded" in idx
    assert "idx_saa_session_recorded" in idx
    assert "idx_saa_recorded_at" in idx


def test_migration_is_idempotent(isolated_db):
    """Running again must not fail."""
    from app.db.migrations.v07_features import _migrate_116_super_agent_activity

    with get_connection() as conn:
        _migrate_116_super_agent_activity(conn)  # second run
    with get_connection() as conn:
        rows = list(conn.execute("SELECT COUNT(*) AS c FROM super_agent_activity"))
        assert rows[0]["c"] == 0
