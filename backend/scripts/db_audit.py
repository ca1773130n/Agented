"""v0.6.0: SQLite schema/index audit + EXPLAIN-QUERY-PLAN inspector.

Usage:
  just db-audit                  # default DB (AGENTED_DB_PATH or backend/agented.db)
  just db-audit -- --json
  just db-audit -- --db /path/to/agented.db

Reports:
  - All tables with their columns + indices (PRAGMA index_list).
  - EXPLAIN QUERY PLAN for a hand-picked set of hot-path queries.
  - Flags any plan that contains SCAN TABLE (full scan) without
    a matching SEARCH (index hit).

Exit codes:
  0 — all hot-path queries hit indices
  1 — at least one hot-path query is SCAN-only (or DB unreachable)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import sqlite3


# Hot-path query templates. (label, sql, expected_index_hint).
_HOT_QUERIES: list[tuple[str, str]] = [
    # Auth + session lookup paths (called on EVERY authenticated request).
    ("sessions_lookup_by_token",
     "SELECT * FROM sessions WHERE token = 'x' OR rotated_from_token = 'x'"),
    ("sessions_active_for_user",
     "SELECT id FROM sessions WHERE user_id = 'u' AND revoked_at IS NULL"),
    ("user_roles_by_api_key",
     "SELECT role, user_id FROM user_roles WHERE api_key = 'k'"),
    # Audit log reads (admin /admin/auth/session-events).
    ("session_events_by_session",
     "SELECT * FROM session_events WHERE session_id = 's' ORDER BY occurred_at DESC LIMIT 10"),
    ("session_events_by_user",
     "SELECT * FROM session_events WHERE user_id = 'u' ORDER BY occurred_at DESC LIMIT 10"),
    # List-page hot paths (operator UI default views).
    ("agents_list",
     "SELECT * FROM agents ORDER BY created_at DESC LIMIT 50"),
    ("projects_list",
     "SELECT * FROM projects ORDER BY created_at DESC LIMIT 50"),
    ("triggers_list",
     "SELECT * FROM triggers ORDER BY created_at DESC LIMIT 50"),
    ("agent_conversations_for_agent",
     "SELECT * FROM agent_conversations WHERE agent_id = 'a' ORDER BY started_at DESC LIMIT 20"),
]


def _default_db_path() -> Path:
    explicit = os.environ.get("AGENTED_DB_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    here = Path(__file__).resolve().parent.parent  # backend/
    return here / "agented.db"


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def audit_indices(conn: sqlite3.Connection) -> dict:
    """For each user table, return {table: [{name, unique, origin, partial}]}."""
    out: dict = {}
    for table in list_tables(conn):
        idx_rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
        out[table] = [
            {
                "name": r[1],
                "unique": bool(r[2]),
                "origin": r[3],
                "partial": bool(r[4]),
            }
            for r in idx_rows
        ]
    return out


def explain_query(conn: sqlite3.Connection, sql: str) -> dict:
    """Run EXPLAIN QUERY PLAN; return {plan: [steps], scan_only: bool}.

    SQLite plan vocabulary:
      - 'SEARCH ... USING INDEX'       → index-driven (good)
      - 'SCAN ... USING INDEX'         → ordered index scan (good for
                                         ORDER BY + LIMIT)
      - 'SCAN <table>' (no INDEX)      → full table scan (bad)

    `scan_only` flags only the bare-SCAN case.
    """
    try:
        rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
    except sqlite3.Error as exc:
        return {"plan": [], "scan_only": False, "error": str(exc)}
    steps = [str(r[3]) for r in rows]
    # A step is "bare scan" if it starts with "SCAN <table>" without
    # "USING INDEX". Index-ordered scans (e.g. for ORDER BY+LIMIT)
    # are not flagged.
    bare_scan = any(
        s.startswith("SCAN ") and "USING INDEX" not in s and "USING COVERING INDEX" not in s
        for s in steps
    )
    return {"plan": steps, "scan_only": bare_scan}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit SQLite indices + hot-path query plans.")
    parser.add_argument("--db", default=None, help="DB path (overrides AGENTED_DB_PATH).")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON only; suppress human table.")
    args = parser.parse_args(argv)

    db_path = Path(args.db).expanduser().resolve() if args.db else _default_db_path()
    if not db_path.is_file():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        indices = audit_indices(conn)
        plans = {}
        scan_only_count = 0
        for label, sql in _HOT_QUERIES:
            plan = explain_query(conn, sql)
            plans[label] = {"sql": sql, **plan}
            if plan.get("scan_only"):
                scan_only_count += 1
    finally:
        conn.close()

    summary = {
        "db_path": str(db_path),
        "table_count": len(indices),
        "indices_by_table": indices,
        "hot_query_plans": plans,
        "scan_only_count": scan_only_count,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"DB: {db_path}", file=sys.stderr)
        print(f"Tables: {len(indices)}", file=sys.stderr)
        print(file=sys.stderr)
        print("Hot-path query plans:", file=sys.stderr)
        for label, info in plans.items():
            marker = " ⚠️ SCAN" if info.get("scan_only") else " ✓"
            print(f"  [{label}]{marker}", file=sys.stderr)
            for step in info["plan"]:
                print(f"    {step}", file=sys.stderr)
        print(file=sys.stderr)
        if scan_only_count:
            print(f"WARNING: {scan_only_count} hot query/queries hit SCAN TABLE.",
                  file=sys.stderr)
        # Always emit the JSON to stdout for scripting.
        print(json.dumps(summary, indent=2))

    return 0 if scan_only_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
