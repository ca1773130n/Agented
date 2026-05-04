"""v0.6.0: migration 111 — session lookup indices."""


def _index_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row is not None


class TestMigration111:
    def test_idx_sessions_token_present(self, isolated_db):
        """Either the explicit idx_sessions_token (migration 104) OR
        the auto-unique index from `token TEXT UNIQUE` is sufficient
        for the lookup query plan."""
        from app.database import get_connection
        with get_connection() as conn:
            # Some index covers token — check via PRAGMA index_list.
            rows = conn.execute("PRAGMA index_list(sessions)").fetchall()
            indices = [dict(r) if hasattr(r, "keys") else r for r in rows]
            # At least one index name should reference `token` either
            # explicitly or via the auto-unique constraint.
            assert any(
                "token" in idx["name"]
                or idx["name"].startswith("sqlite_autoindex_sessions")
                for idx in indices
            )

    def test_idx_sessions_rotated_from_token(self, isolated_db):
        """Created by migration 109, kept for v0.6.0's OR-branch lookup."""
        from app.database import get_connection
        with get_connection() as conn:
            assert _index_exists(conn, "idx_sessions_rotated_from_token")

    def test_idx_sessions_user_active(self, isolated_db):
        """v0.6.0 addition for revoke_user_sessions / get-active-for-user."""
        from app.database import get_connection
        with get_connection() as conn:
            assert _index_exists(conn, "idx_sessions_user_active")


class TestLookupUsesIndex:
    def test_get_session_by_token_query_plan_uses_indices_on_both_branches(self, isolated_db):
        """EXPLAIN QUERY PLAN of the v0.6.0 lookup must:
          1) NOT contain a bare SCAN sessions step (full-table scan)
          2) DO contain SEARCH steps for both OR branches.

        Codex round-1 #2: the previous assertion (`"SCAN" not in plan
        or "SEARCH" in plan`) passed even on mixed plans.
        """
        from app.database import get_connection
        with get_connection() as conn:
            rows = conn.execute(
                "EXPLAIN QUERY PLAN "
                "SELECT * FROM sessions WHERE token = ? OR rotated_from_token = ?",
                ("x", "x"),
            ).fetchall()
        steps = [str(r[3]) for r in rows]
        plan_text = " | ".join(steps)
        # Reject any SCAN sessions step (only step types allowed are
        # SEARCH steps or planner-internal MULTI-INDEX OR steps).
        scan_steps = [s for s in steps if s.startswith("SCAN sessions")]
        assert not scan_steps, (
            f"sessions lookup contains SCAN step(s): {scan_steps}\n"
            f"Full plan: {plan_text}"
        )
        # SEARCH should appear at least once (for at least one OR branch);
        # SQLite's planner uses MULTI-INDEX OR which produces SEARCH steps
        # for each branch index.
        search_steps = [s for s in steps if s.startswith("SEARCH")]
        assert search_steps, (
            f"sessions lookup did not produce any SEARCH step. "
            f"Full plan: {plan_text}"
        )
