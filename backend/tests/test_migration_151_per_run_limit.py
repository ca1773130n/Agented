"""Migration 151: nullable per-run budget ceiling (Harness-1 Phase 3, P6)."""

from app.db.budgets import get_budget_limit, set_budget_limit


def test_migration_151_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 151 in versions
    assert "per_run_budget_limit" in names


def test_fresh_schema_has_column():
    """Call create_fresh_schema DIRECTLY — the isolated_db fixture runs all
    migrations too, so checking the fixture DB would pass even if only the
    migration (not the fresh DDL) added the column (false positive)."""
    import sqlite3

    from app.db.schema import create_fresh_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_limits)")}
    assert "per_run_limit_usd" in cols


def test_migration_151_alter_is_idempotent():
    import sqlite3

    from app.db.migrations.v07_features import _migrate_151_per_run_budget_limit

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE budget_limits (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id TEXT)"
    )
    _migrate_151_per_run_budget_limit(conn)
    _migrate_151_per_run_budget_limit(conn)  # second run must not raise
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_limits)")}
    assert "per_run_limit_usd" in cols


def test_set_and_get_round_trips_per_run_limit():
    assert set_budget_limit("trigger", "t-1", per_run_limit_usd=2.5) is True
    row = get_budget_limit("trigger", "t-1")
    assert row["per_run_limit_usd"] == 2.5
    # Upsert keeps it updatable
    assert set_budget_limit("trigger", "t-1", per_run_limit_usd=3.0) is True
    assert get_budget_limit("trigger", "t-1")["per_run_limit_usd"] == 3.0


def test_set_rejects_nonpositive_per_run_limit():
    """<= 0 is rejected: NULL is the only 'off' state, so the tick's
    `if not limit` check is unambiguous (0.0 can never be stored)."""
    assert set_budget_limit("trigger", "t-2", per_run_limit_usd=-1.0) is False
    assert set_budget_limit("trigger", "t-2", per_run_limit_usd=0.0) is False


def test_budget_route_accepts_per_run_limit():
    from litestar.testing import create_test_client

    from app.db.budgets import get_budget_limit
    from app_litestar.auth import provide_caller
    from app_litestar.routes.budgets import budgets_router  # confirm exact symbol via grep

    with create_test_client(
        route_handlers=[budgets_router], dependencies={"caller": provide_caller}
    ) as client:
        resp = client.put(
            "/admin/budgets/limits",
            json={
                "entity_type": "trigger",
                "entity_id": "bot-pr-review",
                "per_run_limit_usd": 1.5,
            },
        )
    assert resp.status_code in (200, 201)
    assert get_budget_limit("trigger", "bot-pr-review")["per_run_limit_usd"] == 1.5
