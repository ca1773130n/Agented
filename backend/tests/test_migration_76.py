import sqlite3
import pytest
from app.db.migrations import _migrate_76_super_agent_dispatch


def test_migration_adds_dispatch_columns(tmp_path):
    db_path = tmp_path / "migration_76_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE triggers (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE execution_logs (id INTEGER PRIMARY KEY, execution_id TEXT, trigger_id TEXT)")
    conn.commit()

    _migrate_76_super_agent_dispatch(conn)
    conn.commit()

    cur = conn.execute("PRAGMA table_info(triggers)")
    cols = {row[1] for row in cur.fetchall()}
    assert "dispatch_type" in cols
    assert "super_agent_id" in cols

    cur = conn.execute("PRAGMA table_info(execution_logs)")
    cols = {row[1] for row in cur.fetchall()}
    assert "session_id" in cols
    assert "source_type" in cols

    conn.execute("INSERT INTO triggers (id, name) VALUES ('t1', 'test')")
    row = conn.execute("SELECT dispatch_type FROM triggers WHERE id='t1'").fetchone()
    assert row[0] == "bot"

    conn.execute("INSERT INTO execution_logs (execution_id, trigger_id) VALUES ('e1', 't1')")
    row = conn.execute("SELECT source_type FROM execution_logs WHERE execution_id='e1'").fetchone()
    assert row[0] == "bot"

    conn.close()
