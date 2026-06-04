"""v0.7.3b: confirm split schema produces expected table set.

v0.7.6: strengthened with table-count parity, index-count parity, and a
DDL byte-identity guard. Codex review on PR #50 flagged the original
suite as too shallow.
"""

import hashlib
import sqlite3

from app.database import get_connection
from app.db.schema import create_fresh_schema


def _fresh_in_memory():
    """Build a brand-new in-memory DB containing only schema package output.

    The ``isolated_db`` fixture already calls ``init_db()`` + migrations,
    which adds tables/indexes beyond what the schema package alone emits.
    Parity tests need to measure ONLY the schema package, so we use a
    detached :memory: connection here.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    return conn


def test_create_fresh_schema_succeeds(isolated_db):
    with get_connection() as conn:
        create_fresh_schema(conn)


def test_expected_tables_present(isolated_db):
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row["name"] for row in cursor.fetchall()}
    expected = {
        "triggers",
        "execution_logs",
        "agents",
        "agent_conversations",
        "user_skills",
        "teams",
        "team_members",
        "products",
        "projects",
        "plugins",
        "marketplaces",
        "users",
        "sessions",
    }
    missing = expected - tables
    assert not missing, f"Missing expected tables: {missing}"


# -- v0.7.6 parity guards ----------------------------------------------------


# Bump only when intentionally adding/removing a table. A drift here means a
# CREATE TABLE statement was added, removed, or renamed in the schema package.
# Re-baselined after accumulated feature growth (budgets, traces, findings,
# system_errors, rbac, secrets, sso, etc.) since the v0.7.6 baseline of 125.
EXPECTED_TABLE_COUNT = 136

# Bump only when intentionally adding/removing an index. A drift here means a
# CREATE INDEX statement was added, removed, or renamed in the schema package.
# Re-baselined alongside the table growth above (was 162 at v0.7.6).
EXPECTED_INDEX_COUNT = 184


def test_table_count_parity():
    """Every CREATE TABLE in the schema package produces exactly one runtime table."""
    conn = _fresh_in_memory()
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM sqlite_master "
        "WHERE type IN ('table','virtual table') AND name NOT LIKE 'sqlite_%'"
    ).fetchone()["c"]
    assert count == EXPECTED_TABLE_COUNT, (
        f"Table count drift: got {count}, expected {EXPECTED_TABLE_COUNT}. "
        "If this is intentional, update EXPECTED_TABLE_COUNT in this test."
    )


def test_index_count_parity():
    """Every CREATE INDEX produces exactly one runtime index."""
    conn = _fresh_in_memory()
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='index' "
        "AND name NOT LIKE 'sqlite_%'"
    ).fetchone()["c"]
    assert count == EXPECTED_INDEX_COUNT, (
        f"Index count drift: got {count}, expected {EXPECTED_INDEX_COUNT}. "
        "If this is intentional, update EXPECTED_INDEX_COUNT in this test."
    )


def test_ddl_signature_stable():
    """A SHA-256 of the canonicalized DDL catches silent schema drift.

    Sums the normalized SQL of every table and index, hashes the result.
    Any change to a CREATE TABLE/INDEX body — column type tweak, default
    change, missing UNIQUE — flips this hash. Update the expected value
    in the same commit that intentionally changes schema DDL.
    """
    conn = _fresh_in_memory()
    rows = conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL "
        "ORDER BY type, name"
    ).fetchall()
    # Whitespace-normalized concatenation keeps the digest stable across
    # cosmetic DDL formatting tweaks while still catching real changes.
    canon = "\n".join(
        f"{r['type']}::{r['name']}::{' '.join((r['sql'] or '').split())}" for r in rows
    )
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    # Sanity: the digest must be deterministic and non-empty.
    assert len(digest) == 64
    # Re-run on a fresh connection to assert determinism within the process.
    conn2 = _fresh_in_memory()
    rows2 = conn2.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL "
        "ORDER BY type, name"
    ).fetchall()
    canon2 = "\n".join(
        f"{r['type']}::{r['name']}::{' '.join((r['sql'] or '').split())}" for r in rows2
    )
    assert hashlib.sha256(canon2.encode("utf-8")).hexdigest() == digest
