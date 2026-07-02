"""v0.7.8: model_discovery_cache migration shape + idempotence tests."""

from app.database import get_connection


def test_table_exists(isolated_db):
    with get_connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(model_discovery_cache)")}
    expected = {
        "id",
        "backend_kind",
        "auth_method",
        "models_json",
        "discovery_method",
        "discovered_at",
        "expires_at",
        "error_message",
    }
    assert expected.issubset(cols)


def test_indices_exist(isolated_db):
    with get_connection() as conn:
        idx = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='model_discovery_cache'"
            )
        }
    assert "idx_mdc_expires_at" in idx
    assert "idx_mdc_discovered_at" in idx


def test_unique_constraint(isolated_db):
    """Unique on (backend_kind, auth_method)."""
    from app.db import errors

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO model_discovery_cache "
            "(backend_kind, auth_method, models_json, discovery_method, "
            " discovered_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("codex", "api_key", "[]", "subprocess", "2026-01-01", "2026-01-08"),
        )
        conn.commit()
        try:
            conn.execute(
                "INSERT INTO model_discovery_cache "
                "(backend_kind, auth_method, models_json, discovery_method, "
                " discovered_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("codex", "api_key", "[]", "subprocess", "2026-01-01", "2026-01-08"),
            )
            conn.commit()
        except errors.IntegrityError:
            return
    raise AssertionError("expected IntegrityError on duplicate (backend_kind, auth_method)")


def test_migration_is_idempotent(isolated_db):
    """Running again must not fail."""
    from app.db.migrations.v07_features import _migrate_117_model_discovery_cache

    with get_connection() as conn:
        _migrate_117_model_discovery_cache(conn)  # second run
    with get_connection() as conn:
        rows = list(conn.execute("SELECT COUNT(*) AS c FROM model_discovery_cache"))
        assert rows[0]["c"] == 0
