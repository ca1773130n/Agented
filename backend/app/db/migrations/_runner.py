"""Database init + migration runner — split out of migrations.py in v0.7.3c.

This module owns:
- init_db(): the orchestrator called by lifecycle.py.
- Schema-version table helpers.
- _migrate_to_string_ids(): the legacy bots->triggers pre-migration.
- Constants: PREDEFINED_TRIGGERS, VALID_BACKENDS, etc.
- Helpers used by bucket migrations: _validate_sql_identifier, _rebuild_table_fk.

VERSIONED_MIGRATIONS lives in the parent migrations.py orchestrator and is
imported lazily inside init_db / _bootstrap_schema_version to avoid a
circular import (bucket modules import this file).
"""

import logging
import os
import re

import app.config as config

from ..connection import _is_pg, get_connection
from ..ids import generate_trigger_id
from ..schema import create_fresh_schema

logger = logging.getLogger(__name__)

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _table_exists(conn, name: str) -> bool:
    """Backend-agnostic table-existence check.

    Postgres has no ``sqlite_master``; it exposes ``information_schema.tables``
    instead. On SQLite the exact original query is preserved (invariant).
    """
    if _is_pg():
        # MUST scope to the current schema + base tables: information_schema.tables
        # lists every schema the role can see, so an unscoped name='triggers'/'views'
        # matches the built-in information_schema.* system VIEWS and falsely reports
        # existence on a fresh DB (sending init_db down the legacy-replay path).
        # `table_type='BASE TABLE'` mirrors SQLite's `type='table'` (excludes views).
        row = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = ? AND table_schema = current_schema() "
            "AND table_type = 'BASE TABLE'",
            (name,),
        ).fetchone()
        return row is not None
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _validate_sql_identifier(name: str, kind: str = "identifier") -> str:
    """Validate that a string is a safe SQL identifier (table or column name).

    SQLite parameterized queries (?) cannot be used for table/column names,
    so string formatting is necessary for DDL. This function ensures only
    safe alphanumeric + underscore identifiers are allowed.

    Returns the validated name for convenient inline use.
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL {kind}: {name!r}")
    return name


# Valid backend types
VALID_BACKENDS = ("claude", "opencode", "gemini", "codex")

# Valid trigger source values
VALID_TRIGGER_SOURCES = ("webhook", "github", "manual", "scheduled")

# Predefined trigger configurations
# Predefined trigger IDs retain the bot- prefix to preserve historical execution logs,
# PR review records, and external webhook integrations.
PREDEFINED_TRIGGERS = [
    {
        "id": "bot-security",
        "name": "Weekly Security Audit",
        "group_id": 0,  # Deprecated, use match_field_path/match_field_value
        "detection_keyword": "\uc8fc\uac04 \ubcf4\uc548 \ucde8\uc57d\uc810 \uc54c\ub9bc",
        "prompt_template": "/weekly-security-audit {paths}",
        "backend_type": "claude",
        "trigger_source": "webhook",
        "match_field_path": "event.group_id",
        "match_field_value": "4",
        "text_field_path": "event.text",
        "is_predefined": 1,
    },
    {
        "id": "bot-pr-review",
        "name": "PR Review",
        "group_id": 0,  # Not used for GitHub trigger
        "detection_keyword": "",  # Not used for GitHub trigger
        "prompt_template": "/pr-review {pr_url} {pr_title}",
        "backend_type": "claude",
        "trigger_source": "github",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
]

PREDEFINED_TRIGGER_IDS = {t["id"] for t in PREDEFINED_TRIGGERS}

# Backward compatibility aliases
PREDEFINED_TRIGGER_ID = "bot-security"
PREDEFINED_TRIGGER = PREDEFINED_TRIGGERS[0]


# =============================================================================
# Schema version tracking
# =============================================================================


def _ensure_schema_version_table(conn):
    """Create schema_version table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _get_current_version(conn) -> int:
    """Get the highest applied migration version, or 0 if none."""
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0] if row[0] is not None else 0
    except Exception as e:
        logger.debug("Migration version query: %s", e)
        return 0


def _record_version(conn, version: int, name: str):
    """Record a migration as applied."""
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version, name) VALUES (?, ?)",
        (version, name),
    )


def _bootstrap_schema_version(conn):
    """Bootstrap schema_version for existing databases.

    If schema_version table does not exist but triggers table does
    (indicating a post-migration v0.2.x database), create schema_version
    and mark all legacy migrations (1-29) as applied.
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cursor.fetchone():
        return  # Already has version tracking

    _ensure_schema_version_table(conn)

    # Check if this is an existing database (has triggers table)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='triggers'")
    if cursor.fetchone():
        from app.db.migrations import VERSIONED_MIGRATIONS

        # Existing DB — mark all legacy migrations as applied
        for version, name, _func in VERSIONED_MIGRATIONS:
            if version <= 29:
                _record_version(conn, version, name)
        logger.info("Bootstrapped schema_version to version 29 for existing database")


# =============================================================================
# Database initialization
# =============================================================================


def init_db():
    """Initialize database tables."""
    # Lazy imports avoid the circular dep: bucket modules import this _runner,
    # and the parent migrations.py module assembles VERSIONED_MIGRATIONS from buckets.
    from app.db.migrations import VERSIONED_MIGRATIONS
    from app.db.migrations.v04_initial import _migrate_add_github_columns

    with get_connection() as conn:
        # Enable WAL mode for concurrent read/write safety (SQLite only — journal
        # modes/PRAGMA don't exist on Postgres, which manages WAL internally).
        if not _is_pg():
            result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
            if result[0].lower() != "wal":
                logger.warning("WAL mode not enabled, got: %s", result[0])
            else:
                logger.info("SQLite WAL mode enabled")

        # Check if we need to migrate from old schema (INTEGER id) to new (TEXT id)
        # Check for either legacy bots table or current triggers table
        has_bots = _table_exists(conn, "bots")
        has_triggers = _table_exists(conn, "triggers")

        if has_bots or has_triggers:
            if has_bots:
                # Legacy bots table exists, check if migration needed
                cursor = conn.execute("PRAGMA table_info(bots)")
                columns = {row[1]: row[2] for row in cursor.fetchall()}
                if columns.get("id") == "INTEGER":
                    logger.info("Migrating database to new schema with string bot IDs...")
                    _migrate_to_string_ids(conn)
                    _migrate_add_github_columns(conn)
                    conn.commit()
                    return

            # Bootstrap schema_version for existing databases
            _bootstrap_schema_version(conn)

            # Run version-gated migrations
            current_version = _get_current_version(conn)
            for version, name, func in VERSIONED_MIGRATIONS:
                if version > current_version:
                    logger.info(f"Running migration {version}: {name}")
                    try:
                        func(conn)
                        _record_version(conn, version, name)
                    except Exception as e:
                        logger.error(
                            "Migration %d (%s) failed: %s — database will be rolled back to "
                            "version %d. Fix the migration before restarting.",
                            version,
                            name,
                            e,
                            current_version,
                            exc_info=True,
                        )
                        raise RuntimeError(f"Migration {version} ({name}) failed: {e}") from e

            conn.commit()

            # Mark stale running executions from previous sessions
            stale_count = _mark_stale_executions(conn)
            if stale_count > 0:
                logger.info(
                    "Marked %d stale execution(s) as interrupted from previous session", stale_count
                )
            return

        # Fresh database — create all tables from schema.py
        create_fresh_schema(conn)
        _ensure_schema_version_table(conn)
        # Run only v0.3.0 migration functions (30+) for new tables.
        # Legacy migrations (1-29) operate on bots/triggers transition
        # and are not safe to run on a fresh schema that already has triggers.
        for version, name, func in VERSIONED_MIGRATIONS:
            if version >= 30:
                func(conn)
            _record_version(conn, version, name)
        # Create tables that exist only in legacy migration code, not in fresh schema
        _create_migration_only_tables(conn)
        conn.commit()


# =============================================================================
# Helpers
# =============================================================================


def _mark_stale_executions(conn) -> int:
    """Mark running executions from previous sessions as interrupted. Returns count affected."""
    cursor = conn.execute(
        "UPDATE execution_logs SET status = 'interrupted', finished_at = datetime('now') WHERE status = 'running'"
    )
    conn.commit()
    return cursor.rowcount


def _create_migration_only_tables(conn):
    """Create tables that exist only in migration code, not in fresh schema.

    These 4 tables (settings, ai_backends, backend_accounts, design_conversations)
    were historically created by migration functions that also operate on the legacy
    bots table. Since the fresh schema path uses triggers (not bots), those migration
    functions cannot run on a fresh database. This function creates the tables directly.
    """
    # Settings table (from _migrate_add_marketplaces_and_team_agents)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # AI backends table (from _migrate_add_agent_effort_and_ai_backends)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_backends (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            icon TEXT,
            documentation_url TEXT,
            is_installed INTEGER DEFAULT 0,
            version TEXT,
            models TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed predefined backends
    predefined_backends = [
        (
            "backend-claude",
            "Claude Code",
            "claude",
            "Anthropic's Claude AI assistant for coding",
            "claude",
            "https://docs.anthropic.com",
            '["Opus 4.6", "Sonnet 4.5", "Haiku 4.5"]',
        ),
        (
            "backend-opencode",
            "OpenCode",
            "opencode",
            "Open-source terminal coding assistant",
            "opencode",
            "https://opencode.dev",
            '["Claude Sonnet 4.5", "Gemini 2.5 Flash"]',
        ),
        (
            "backend-gemini",
            "Gemini CLI",
            "gemini",
            "Google's Gemini AI for coding",
            "gemini",
            "https://ai.google.dev",
            '["Gemini 2.5 Pro", "Gemini 2.5 Flash"]',
        ),
        (
            "backend-codex",
            "Codex CLI",
            "codex",
            "OpenAI's coding agent",
            "codex",
            "https://openai.com",
            '["o4-mini", "o3", "GPT-4.1"]',
        ),
    ]
    for backend in predefined_backends:
        conn.execute(
            "INSERT OR IGNORE INTO ai_backends (id, name, type, description, icon, documentation_url, models) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            backend,
        )

    # Backend accounts table (from _migrate_add_agent_effort_and_ai_backends)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backend_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backend_id TEXT NOT NULL,
            account_name TEXT NOT NULL,
            email TEXT,
            config_path TEXT,
            api_key_env TEXT,
            is_default INTEGER DEFAULT 0,
            plan TEXT,
            usage_data TEXT,
            rate_limited_until TIMESTAMP,
            rate_limit_reason TEXT,
            last_used_at TIMESTAMP,
            total_executions INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (backend_id) REFERENCES ai_backends(id) ON DELETE CASCADE
        )
    """)

    # Design conversations table (from _migrate_add_design_conversations_table)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS design_conversations (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            status TEXT DEFAULT 'active',
            messages TEXT DEFAULT '[]',
            config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dc_entity_type ON design_conversations(entity_type)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dc_status ON design_conversations(status)")


_REBUILD_TABLE_ALLOWLIST = {"project_paths", "execution_logs", "pr_reviews"}


def _rebuild_table_fk(conn, table_name):
    """Rebuild a table to fix FK references from bots to triggers.

    Uses the CREATE new table, INSERT INTO...SELECT, DROP old, RENAME pattern.
    """
    _validate_sql_identifier(table_name, "table name")
    if table_name not in _REBUILD_TABLE_ALLOWLIST:
        raise ValueError(
            f"Table '{table_name}' is not in the FK rebuild allowlist: "
            f"{sorted(_REBUILD_TABLE_ALLOWLIST)}"
        )

    # Get the current CREATE TABLE statement
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    )
    row = cursor.fetchone()
    if not row:
        return

    create_sql = row[0]
    # Replace bots references with triggers
    new_sql = create_sql.replace("REFERENCES bots(", "REFERENCES triggers(")
    new_sql = new_sql.replace(f"CREATE TABLE {table_name}", f"CREATE TABLE {table_name}_new")

    conn.execute(new_sql)
    conn.execute(f"INSERT INTO {table_name}_new SELECT * FROM {table_name}")
    conn.execute(f"DROP TABLE {table_name}")
    conn.execute(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")


# =============================================================================
# Migration functions (in exact original execution order)
# =============================================================================


def _migrate_to_string_ids(conn):
    """Migrate from INTEGER bot IDs to TEXT bot IDs."""
    # Get existing data
    cursor = conn.execute("SELECT * FROM bots")
    old_bots = [dict(row) for row in cursor.fetchall()]

    cursor = conn.execute("SELECT * FROM project_paths")
    old_paths = [dict(row) for row in cursor.fetchall()]

    # Create ID mapping (old int -> new string)
    id_mapping = {}
    for bot in old_bots:
        old_id = bot["id"]
        if bot["is_predefined"]:
            new_id = PREDEFINED_TRIGGER_ID
        else:
            new_id = generate_trigger_id()
        id_mapping[old_id] = new_id

    # Drop old tables
    conn.execute("DROP TABLE IF EXISTS project_paths")
    conn.execute("DROP TABLE IF EXISTS bots")

    # Create new tables with TEXT id
    conn.execute("""
        CREATE TABLE bots (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            group_id INTEGER NOT NULL,
            detection_keyword TEXT NOT NULL,
            prompt_template TEXT NOT NULL,
            backend_type TEXT NOT NULL DEFAULT 'claude',
            is_predefined INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE project_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT NOT NULL,
            local_project_path TEXT NOT NULL,
            symlink_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE,
            UNIQUE(bot_id, local_project_path)
        )
    """)

    # Execution logs table for bot execution history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL UNIQUE,
            bot_id TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            duration_ms INTEGER,
            prompt TEXT,
            backend_type TEXT NOT NULL,
            command TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            exit_code INTEGER,
            error_message TEXT,
            stdout_log TEXT,
            stderr_log TEXT,
            FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_logs_bot_id ON execution_logs(bot_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_logs_started_at ON execution_logs(started_at DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_logs_status ON execution_logs(status)")

    # Re-insert bots with new IDs
    for bot in old_bots:
        new_id = id_mapping[bot["id"]]
        conn.execute(
            """
            INSERT INTO bots (id, name, group_id, detection_keyword, prompt_template, backend_type, is_predefined, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                new_id,
                bot["name"],
                bot["group_id"],
                bot["detection_keyword"],
                bot["prompt_template"],
                bot["backend_type"],
                bot["is_predefined"],
                bot["enabled"],
                bot["created_at"],
            ),
        )

    # Re-insert paths with new bot IDs and update symlink names
    for path in old_paths:
        old_bot_id = path["bot_id"]
        new_bot_id = id_mapping.get(old_bot_id)
        if new_bot_id:
            old_symlink = path.get("symlink_name")
            new_symlink = None

            # Rename symlink if it exists
            if old_symlink:
                # Generate new symlink name with new bot_id
                basename = old_symlink.split("_", 1)[1] if "_" in old_symlink else old_symlink
                new_symlink = f"{new_bot_id}_{basename}"

                old_symlink_path = os.path.join(config.SYMLINK_DIR, old_symlink)
                new_symlink_path = os.path.join(config.SYMLINK_DIR, new_symlink)

                if os.path.islink(old_symlink_path):
                    target = os.readlink(old_symlink_path)
                    os.unlink(old_symlink_path)
                    os.symlink(target, new_symlink_path)
                    logger.info("Renamed symlink: %s -> %s", old_symlink, new_symlink)

            conn.execute(
                """
                INSERT INTO project_paths (bot_id, local_project_path, symlink_name, created_at)
                VALUES (?, ?, ?, ?)
            """,
                (new_bot_id, path["local_project_path"], new_symlink, path["created_at"]),
            )

    conn.commit()
    logger.info("Migration complete. Migrated %d bots and %d paths.", len(old_bots), len(old_paths))
