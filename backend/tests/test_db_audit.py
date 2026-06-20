"""v0.6.0: db_audit script tests."""

import json
import sqlite3


def _seed_minimal_db(path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE sessions (id INTEGER, token TEXT, rotated_from_token TEXT, user_id TEXT, revoked_at TIMESTAMP)"
    )
    conn.execute("CREATE INDEX idx_sessions_token ON sessions(token)")
    # SQLite needs both branches indexed for OR-clause optimization.
    conn.execute("CREATE INDEX idx_sessions_rotated_from_token ON sessions(rotated_from_token)")
    conn.execute("CREATE TABLE user_roles (id INTEGER, api_key TEXT, role TEXT, user_id TEXT)")
    conn.execute("CREATE INDEX idx_user_roles_api_key ON user_roles(api_key)")
    conn.execute(
        "CREATE TABLE session_events (id INTEGER, session_id TEXT, user_id TEXT, occurred_at TIMESTAMP)"
    )
    conn.execute("CREATE INDEX idx_session_events_session_id ON session_events(session_id)")
    conn.execute("CREATE INDEX idx_session_events_user_id ON session_events(user_id)")
    conn.commit()
    conn.close()


class TestAuditIndices:
    def test_lists_tables_and_indices(self, tmp_path):
        from scripts.db_audit import audit_indices

        db = tmp_path / "x.db"
        _seed_minimal_db(db)
        conn = sqlite3.connect(str(db))
        try:
            result = audit_indices(conn)
        finally:
            conn.close()
        assert "sessions" in result
        assert any(idx["name"] == "idx_sessions_token" for idx in result["sessions"])
        assert "user_roles" in result
        assert "session_events" in result


class TestExplainQuery:
    def test_search_classification_when_indexed(self, tmp_path):
        from scripts.db_audit import explain_query

        db = tmp_path / "x.db"
        _seed_minimal_db(db)
        conn = sqlite3.connect(str(db))
        try:
            plan = explain_query(
                conn,
                "SELECT * FROM sessions WHERE token = 'k' OR rotated_from_token = 'k'",
            )
        finally:
            conn.close()
        # idx_sessions_token covers the token branch.
        text = " | ".join(plan["plan"])
        assert "SEARCH" in text
        assert plan["scan_only"] is False

    def test_scan_classification_when_no_index(self, tmp_path):
        from scripts.db_audit import explain_query

        db = tmp_path / "x.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE bare (id INTEGER, name TEXT)")
        conn.commit()
        try:
            plan = explain_query(conn, "SELECT * FROM bare WHERE name = 'x'")
        finally:
            conn.close()
        assert plan["scan_only"] is True


class TestCLI:
    def test_main_emits_json_and_exits_0_on_indexed_schema(self, tmp_path, capsys):
        from scripts.db_audit import main

        db = tmp_path / "x.db"
        _seed_minimal_db(db)
        # Add the rotated_from_token + user_id+revoked_at indices so all hot
        # queries hit indices.
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE INDEX idx_rot ON sessions(rotated_from_token)")
        conn.execute("CREATE INDEX idx_user_active ON sessions(user_id, revoked_at)")
        conn.commit()
        conn.close()
        rc = main(["--db", str(db), "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        summary = json.loads(out)
        assert summary["scan_only_count"] == 0
        assert "hot_query_plans" in summary

    def test_main_exits_1_when_db_missing(self, tmp_path, capsys):
        from scripts.db_audit import main

        rc = main(["--db", str(tmp_path / "nope.db"), "--json"])
        assert rc == 1
