"""Migrations for v0.6.0 track — split out of migrations.py in v0.7.3c.

Function bodies are byte-identical copies from the original migrations.py.
"""

import logging

from ._runner import _validate_sql_identifier

logger = logging.getLogger(__name__)


def _add_user_id_column(conn, table: str) -> None:
    """Idempotent helper: add user_id column + backfill + index for *table*.

    Used by every owned-entity multi-tenancy migration from wave 41 onward.
    Walking the table list explicitly (rather than a single mega-migration)
    keeps each migration version atomic — if a future schema change breaks
    one table, only that one's migration needs a fix.
    """
    table = _validate_sql_identifier(table, "table")
    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if "user_id" in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT REFERENCES users(id)")
    conn.execute(
        f"UPDATE {table} SET user_id = (SELECT id FROM users WHERE email = ?) "
        f"WHERE user_id IS NULL",
        ("legacy@local",),
    )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")


def _migrate_106_owned_entities_batch1_user_id(conn):
    """Multi-tenancy starter — 5 tables (track B, wave 41)."""
    for table in ("projects", "teams", "agents", "plugins", "super_agents"):
        _add_user_id_column(conn, table)


def _migrate_108_password_reset_tokens(conn):
    """Forgot-password support — single-use tokens (track B, wave 43).

    The reset email side is intentionally NOT wired (no SMTP infra in
    this codebase yet). The endpoint logs the reset link to stderr,
    which is enough for local dev / single-operator setups.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            token TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            consumed_at TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prt_token ON password_reset_tokens(token)")


def _migrate_109_session_audit_columns(conn):
    """v0.5.12: session audit + lifecycle hardening.

    Adds three columns to `sessions` for rotation grace window and
    revocation tracking, and creates the `session_events` audit table.

    PRAGMA + ALTER is not atomic — two concurrent boots can both see a
    missing column and both ALTER, with the second raising "duplicate
    column name". Catching that error makes the migration idempotent
    under concurrent invocation (`just deploy` + ad-hoc CLI overlap).
    """
    import sqlite3

    def _add_column_if_missing(name: str, ddl_type: str) -> None:
        cursor = conn.execute("PRAGMA table_info(sessions)")
        existing = {row[1] for row in cursor.fetchall()}
        if name in existing:
            return
        try:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {ddl_type}")
        except sqlite3.OperationalError as exc:
            # Concurrent boot won the race; column now exists.
            if "duplicate column name" not in str(exc).lower():
                raise

    # 1. Add columns to sessions (idempotent: PRAGMA + duplicate-column-safe).
    _add_column_if_missing("rotated_from_token", "TEXT")
    _add_column_if_missing("revoked_at", "TIMESTAMP")
    _add_column_if_missing("revoke_reason", "TEXT")

    # 2. Create session_events audit table.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_id TEXT,
            event_type TEXT NOT NULL,
            occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT,
            metadata TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_events_session_id ON session_events(session_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session_events_user_id ON session_events(user_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_events_occurred_at "
        "ON session_events(occurred_at DESC)"
    )

    # 3. Index for grace-window lookup.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_rotated_from_token ON sessions(rotated_from_token)"
    )


def _migrate_110_session_rotated_at(conn):
    """v0.5.12: anchor the rotation grace window to a stable timestamp.

    Migration 109 used `last_used_at` for the rotation grace window,
    but that column is also refreshed on every successful auth — so
    an attacker holding an old token could replay it indefinitely,
    each replay sliding the 5-second window forward. Add a
    `rotated_at` column set only by `rotate_session`, never by the
    per-request touch.
    """
    import sqlite3

    cursor = conn.execute("PRAGMA table_info(sessions)")
    existing = {row[1] for row in cursor.fetchall()}
    if "rotated_at" not in existing:
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN rotated_at TIMESTAMP")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def _migrate_113_rotated_from_token_unique(conn):
    """v0.6.1: enforce uniqueness on `rotated_from_token` via partial
    unique index. Token rotation logic already maintains this in
    practice (each rotation captures the previous unique token), but
    the schema didn't enforce it — Codex round-1 #7 of v0.6.0 flagged
    this as a deferrable theoretical gap. v0.6.1 closes it.

    Partial unique index covers only non-NULL values; non-rotated
    sessions (NULL rotated_from_token) don't conflict. SQLite has
    supported partial indices since 3.8.0; the test suite runs on
    3.40+.

    Codex round-1 D: preflight dedup on populated DBs. If any
    `rotated_from_token` values are duplicated, the older row's
    pointer is nulled out (the session itself stays valid — just
    loses the historical "rotated from X" backlink). A WARN is
    logged so the operator can audit post-deploy.
    """
    import logging

    log = logging.getLogger(__name__)

    # Preflight: find duplicates (newer row by id wins; older nulled).
    duplicates = conn.execute(
        "SELECT rotated_from_token, COUNT(*) AS n FROM sessions "
        "WHERE rotated_from_token IS NOT NULL "
        "GROUP BY rotated_from_token HAVING COUNT(*) > 1"
    ).fetchall()
    if duplicates:
        for row in duplicates:
            dup_token, n = row[0], row[1]
            log.warning(
                "migration 113: %d sessions share rotated_from_token=%r; "
                "nulling out older rows to satisfy the new unique index.",
                n,
                dup_token[:8] + "..." if len(dup_token) > 8 else dup_token,
            )
            # Keep the row with the largest (most-recent) id; null the rest.
            conn.execute(
                "UPDATE sessions SET rotated_from_token = NULL "
                "WHERE rotated_from_token = ? AND id NOT IN ("
                "  SELECT id FROM sessions WHERE rotated_from_token = ? "
                "  ORDER BY id DESC LIMIT 1"
                ")",
                (dup_token, dup_token),
            )
        conn.commit()

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_rotated_from_token_unique "
        "ON sessions(rotated_from_token) "
        "WHERE rotated_from_token IS NOT NULL"
    )


def _migrate_112_list_page_indices(conn):
    """v0.6.0 round-1: indices for the operator-UI default list pages.

    db_audit revealed that `projects` and `triggers` ORDER BY created_at
    DESC LIMIT 50 fell back to full-table-scan + temp B-tree sort. Add
    descending indices so the ORDER BY can stream from the index.
    """
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_triggers_created_at ON triggers(created_at DESC)")


def _migrate_111_session_lookup_indices(conn):
    """v0.6.0: indices for fast session lookup.

    The v0.5.12 get_session_by_token did SELECT * FROM sessions and
    iterated with hmac.compare_digest. For correctness this was fine
    (and the sessions table is small in practice), but it scales
    O(n) with active session count. The v0.6.0 lookup uses
    `WHERE token = ? OR rotated_from_token = ?` which needs indices
    on both predicates.

    Migration 104 already creates a non-unique idx_sessions_token
    AND the table-level `token TEXT UNIQUE NOT NULL` constraint
    creates an auto-unique index (sqlite_autoindex_sessions_2).
    Migration 109 already creates idx_sessions_rotated_from_token.
    We only add the user_active covering index that wasn't there.
    """
    # Covering index for revoke_user_sessions / get_active_for_user
    # paths (`WHERE user_id = ? AND revoked_at IS NULL`).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_active ON sessions(user_id, revoked_at)"
    )


def _migrate_107_owned_entities_batch2_user_id(conn):
    """Multi-tenancy — remaining owned-entity tables (track B, wave 42).

    Covers hooks, commands, rules, triggers, mcp_servers, sketches,
    workflows, user_skills, agent_conversations, design_conversations.
    audit_events intentionally excluded — those are immutable system
    events without an owning user.
    """
    for table in (
        "hooks",
        "commands",
        "rules",
        "triggers",
        "mcp_servers",
        "sketches",
        "workflows",
        "user_skills",
        "agent_conversations",
        "design_conversations",
    ):
        _add_user_id_column(conn, table)


def _migrate_105_products_user_id(conn):
    """Per-entity multi-tenancy starter (track B, wave 39).

    Adds an optional user_id column to ``products`` and backfills every
    existing row to the synthetic legacy@local user. The column stays
    nullable so existing schema-level INSERTs continue to work — the DB
    layer (``app/db/products.py``) handles the default.

    This is the *pattern* for the remaining 24 owned-entity tables.
    Subsequent migrations will repeat it for projects, teams, agents,
    plugins, and so on. Each table gets:
      1. ALTER TABLE ... ADD COLUMN user_id TEXT REFERENCES users(id)
      2. UPDATE ... SET user_id = legacy_user WHERE user_id IS NULL
      3. CREATE INDEX idx_<table>_user_id ON <table>(user_id)
    """
    cursor = conn.execute("PRAGMA table_info(products)")
    existing = {row[1] for row in cursor.fetchall()}
    if "user_id" in existing:
        return  # idempotent

    conn.execute("ALTER TABLE products ADD COLUMN user_id TEXT REFERENCES users(id)")
    conn.execute(
        "UPDATE products SET user_id = (SELECT id FROM users WHERE email = ?) "
        "WHERE user_id IS NULL",
        ("legacy@local",),
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_user_id ON products(user_id)")


def _migrate_104_sessions_table(conn):
    """Sessions table for the login endpoint (track B, wave 32)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            token TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")


def _migrate_103_users_password_hash(conn):
    """Add password_hash column to users (track B, wave 31).

    Nullable so the legacy@local user (and any pre-existing users) keep
    working; password-required entry points (login flow, wave 32+) will
    reject users with NULL hashes.
    """
    cursor = conn.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in cursor.fetchall()}
    if "password_hash" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")


def _migrate_102_user_roles_user_id(conn):
    """Add user_id column to user_roles and backfill existing rows.

    Track B, wave 20. Schema becomes multi-user-ready while preserving
    single-user behaviour: every existing user_roles row is reassigned
    to a synthetic "legacy@local" user so authorization keeps working.
    """
    cursor = conn.execute("PRAGMA table_info(user_roles)")
    existing = {row[1] for row in cursor.fetchall()}
    if "user_id" in existing:
        return  # idempotent

    legacy_row = conn.execute("SELECT id FROM users WHERE email = ?", ("legacy@local",)).fetchone()
    if legacy_row:
        legacy_id = legacy_row[0]
    else:
        legacy_id = "user-legacy"
        conn.execute(
            """INSERT INTO users (id, email, display_name, is_active)
               VALUES (?, ?, ?, 1)""",
            (legacy_id, "legacy@local", "Legacy single-user"),
        )

    conn.execute("ALTER TABLE user_roles ADD COLUMN user_id TEXT REFERENCES users(id)")
    conn.execute(
        "UPDATE user_roles SET user_id = ? WHERE user_id IS NULL",
        (legacy_id,),
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id)")


def _migrate_101_users_table(conn):
    """Add the users table — foundation for multi-user mode (track B).

    Schema-only: no application code consumes the table yet (waves 20-21
    will wire the FK from user_roles + the ContextVar plumbing). Existing
    deployments stay in single-user mode through an optional FK that
    defaults to NULL.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)")


def _migrate_114_trigger_events(conn):
    """v0.7.1: capture incoming webhook payloads in DB for inspection + replay.

    `trigger_id` is intentionally nullable + no FK CASCADE — we keep
    history if the trigger row is deleted, and we also record unmatched
    webhooks (no trigger_id) so debugging works for "trigger didn't fire"
    reports.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trigger_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_id TEXT,
            received_at TIMESTAMP NOT NULL,
            payload TEXT NOT NULL,
            signature_header TEXT,
            matched INTEGER NOT NULL DEFAULT 0,
            dispatch_status TEXT,
            dispatch_error TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trigger_events_trigger_id "
        "ON trigger_events(trigger_id, received_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trigger_events_received_at ON trigger_events(received_at)"
    )


def _migrate_115_execution_logs_trigger_started_index(conn):
    """v0.7.0: composite index for per-bot SLA queries.

    The bot-health rollup runs one
    `SELECT … FROM execution_logs WHERE trigger_id = ? AND started_at >= ?`
    per trigger. Without a composite index, SQLite falls back to the
    started_at index and re-filters trigger_id per row, repeated for
    every bot. The composite (trigger_id, started_at DESC) lets the
    planner do a single SEARCH per bot, which is the difference
    between O(bots * runs) and O(bots * runs_in_window).
    """
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_logs_trigger_started "
        "ON execution_logs(trigger_id, started_at DESC)"
    )


V06_MIGRATIONS = [
    # multi-user foundation (track B)
    (101, "users_table", _migrate_101_users_table),
    (102, "user_roles_user_id", _migrate_102_user_roles_user_id),
    (103, "users_password_hash", _migrate_103_users_password_hash),
    (104, "sessions_table", _migrate_104_sessions_table),
    (105, "products_user_id", _migrate_105_products_user_id),
    (106, "owned_entities_batch1", _migrate_106_owned_entities_batch1_user_id),
    (107, "owned_entities_batch2", _migrate_107_owned_entities_batch2_user_id),
    (108, "password_reset_tokens", _migrate_108_password_reset_tokens),
    # v0.5.12 auth depth: session audit + lifecycle hardening
    (109, "session_audit_columns", _migrate_109_session_audit_columns),
    # v0.5.12 round-3 fix: separate rotation timestamp so grace window
    # cannot be slid forward by replaying the rotated_from_token.
    (110, "session_rotated_at", _migrate_110_session_rotated_at),
    # v0.6.0 perf: indices for fast session lookup.
    (111, "session_lookup_indices", _migrate_111_session_lookup_indices),
    # v0.6.0 round-1: list-page ORDER BY indices (Codex-flagged).
    (112, "list_page_indices", _migrate_112_list_page_indices),
    # v0.6.1: enforce rotated_from_token uniqueness (v0.6.0 deferred).
    (113, "rotated_from_token_unique", _migrate_113_rotated_from_token_unique),
    # v0.7.1: trigger payload capture for inspector + replay.
    (114, "trigger_events", _migrate_114_trigger_events),
    # v0.7.0 round-1 (Codex): composite index for bot-health rollup query.
    (
        115,
        "execution_logs_trigger_started_index",
        _migrate_115_execution_logs_trigger_started_index,
    ),
]
