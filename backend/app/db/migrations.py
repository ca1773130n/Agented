"""Database initialization, migrations, and seeding for Agented.

This module is EXEMPT from the 500-line limit because migration code is an
append-only historical record that is never edited once written.
"""

import logging
import os
import sqlite3

import app.config as config

from .connection import get_connection
from .ids import _get_unique_mcp_server_id, generate_trigger_id
from .schema import create_fresh_schema

logger = logging.getLogger(__name__)

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
    with get_connection() as conn:
        # Enable WAL mode for concurrent read/write safety
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if result[0].lower() != "wal":
            print(f"WARNING: WAL mode not enabled, got: {result[0]}")
        else:
            print("SQLite WAL mode enabled")

        # Check if we need to migrate from old schema (INTEGER id) to new (TEXT id)
        # Check for either legacy bots table or current triggers table
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bots'")
        has_bots = cursor.fetchone()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='triggers'"
        )
        has_triggers = cursor.fetchone()

        if has_bots or has_triggers:
            if has_bots:
                # Legacy bots table exists, check if migration needed
                cursor = conn.execute("PRAGMA table_info(bots)")
                columns = {row[1]: row[2] for row in cursor.fetchall()}
                if columns.get("id") == "INTEGER":
                    print("Migrating database to new schema with string bot IDs...")
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
                    func(conn)
                    _record_version(conn, version, name)

            conn.commit()

            # Mark stale running executions from previous sessions
            stale_count = _mark_stale_executions(conn)
            if stale_count > 0:
                print(
                    f"Marked {stale_count} stale execution(s) as interrupted from previous session"
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


def _rebuild_table_fk(conn, table_name):
    """Rebuild a table to fix FK references from bots to triggers.

    Uses the CREATE new table, INSERT INTO...SELECT, DROP old, RENAME pattern.
    """
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
                    print(f"Renamed symlink: {old_symlink} -> {new_symlink}")

            conn.execute(
                """
                INSERT INTO project_paths (bot_id, local_project_path, symlink_name, created_at)
                VALUES (?, ?, ?, ?)
            """,
                (new_bot_id, path["local_project_path"], new_symlink, path["created_at"]),
            )

    conn.commit()
    print(f"Migration complete. Migrated {len(old_bots)} bots and {len(old_paths)} paths.")


def _migrate_add_github_columns(conn):
    """Add path_type/github_repo_url to project_paths and auto_resolve to bots if missing."""
    # Check project_paths columns
    cursor = conn.execute("PRAGMA table_info(project_paths)")
    pp_columns = {row[1] for row in cursor.fetchall()}

    if "path_type" not in pp_columns:
        conn.execute("ALTER TABLE project_paths ADD COLUMN path_type TEXT NOT NULL DEFAULT 'local'")
        print("Added path_type column to project_paths")
    if "github_repo_url" not in pp_columns:
        conn.execute("ALTER TABLE project_paths ADD COLUMN github_repo_url TEXT")
        print("Added github_repo_url column to project_paths")

    # Check bots columns
    cursor = conn.execute("PRAGMA table_info(bots)")
    bots_columns = {row[1] for row in cursor.fetchall()}

    if "auto_resolve" not in bots_columns:
        conn.execute("ALTER TABLE bots ADD COLUMN auto_resolve INTEGER DEFAULT 0")
        print("Added auto_resolve column to bots")

    conn.commit()


def _migrate_add_pr_reviews_table(conn):
    """Create pr_reviews table if it doesn't exist (for existing databases)."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pr_reviews'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pr_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL DEFAULT 'bot-pr-review',
                project_name TEXT NOT NULL,
                github_repo_url TEXT,
                pr_number INTEGER NOT NULL,
                pr_url TEXT NOT NULL,
                pr_title TEXT NOT NULL,
                pr_author TEXT,
                pr_status TEXT NOT NULL DEFAULT 'open',
                review_status TEXT NOT NULL DEFAULT 'pending',
                review_comment TEXT,
                fixes_applied INTEGER DEFAULT 0,
                fix_comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_reviews_bot_id ON pr_reviews(bot_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_reviews_pr_status ON pr_reviews(pr_status)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pr_reviews_review_status ON pr_reviews(review_status)"
        )
        conn.commit()
        print("Created pr_reviews table")


def _migrate_add_trigger_source(conn):
    """Add trigger_source column to bots table if it doesn't exist."""
    cursor = conn.execute("PRAGMA table_info(bots)")
    columns = {row[1] for row in cursor.fetchall()}

    if "trigger_source" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN trigger_source TEXT NOT NULL DEFAULT 'webhook'")
        conn.commit()
        print("Added trigger_source column to bots")


def _migrate_add_schedule_columns(conn):
    """Add schedule configuration columns for scheduled bots."""
    cursor = conn.execute("PRAGMA table_info(bots)")
    columns = {row[1] for row in cursor.fetchall()}

    added_columns = []
    if "schedule_type" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN schedule_type TEXT")
        added_columns.append("schedule_type")
    if "schedule_time" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN schedule_time TEXT")
        added_columns.append("schedule_time")
    if "schedule_day" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN schedule_day INTEGER")
        added_columns.append("schedule_day")
    if "schedule_timezone" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN schedule_timezone TEXT DEFAULT 'Asia/Seoul'")
        added_columns.append("schedule_timezone")
    if "next_run_at" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN next_run_at TIMESTAMP")
        added_columns.append("next_run_at")
    if "last_run_at" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN last_run_at TIMESTAMP")
        added_columns.append("last_run_at")

    if added_columns:
        conn.commit()
        print(f"Added schedule columns to bots: {', '.join(added_columns)}")


def _migrate_add_skill_command(conn):
    """Add skill_command column to bots table if it doesn't exist."""
    cursor = conn.execute("PRAGMA table_info(bots)")
    columns = {row[1] for row in cursor.fetchall()}

    if "skill_command" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN skill_command TEXT")
        conn.commit()
        print("Added skill_command column to bots")


def _migrate_add_model_column(conn):
    """Add model column to bots table if it doesn't exist."""
    cursor = conn.execute("PRAGMA table_info(bots)")
    columns = {row[1] for row in cursor.fetchall()}

    if "model" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN model TEXT")
        conn.commit()
        print("Added model column to bots")


def _migrate_add_agents_tables(conn):
    """Create agents and agent_conversations tables if they don't exist."""
    # Check if agents table exists
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agents'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                role TEXT,
                goals TEXT,
                context TEXT,
                backend_type TEXT NOT NULL DEFAULT 'claude',
                enabled INTEGER DEFAULT 1,
                skills TEXT,
                documents TEXT,
                system_prompt TEXT,
                creation_conversation_id TEXT,
                creation_status TEXT DEFAULT 'completed',
                triggers TEXT,
                color TEXT,
                icon TEXT,
                model TEXT,
                temperature REAL,
                tools TEXT,
                autonomous INTEGER DEFAULT 0,
                allowed_tools TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_enabled ON agents(enabled)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_created_at ON agents(created_at DESC)")
        conn.commit()
        print("Created agents table")
    else:
        # Migrate existing agents table to add new harness fields
        cursor = conn.execute("PRAGMA table_info(agents)")
        columns = {row[1] for row in cursor.fetchall()}
        new_columns = [
            ("triggers", "TEXT"),
            ("color", "TEXT"),
            ("icon", "TEXT"),
            ("model", "TEXT"),
            ("temperature", "REAL"),
            ("tools", "TEXT"),
            ("autonomous", "INTEGER DEFAULT 0"),
            ("allowed_tools", "TEXT"),
        ]
        for col_name, col_type in new_columns:
            if col_name not in columns:
                conn.execute(f"ALTER TABLE agents ADD COLUMN {col_name} {col_type}")
        conn.commit()

    # Check if agent_conversations table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_conversations'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_conversations (
                id TEXT PRIMARY KEY,
                agent_id TEXT,
                status TEXT DEFAULT 'active',
                messages TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_conversations_status ON agent_conversations(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_conversations_agent_id ON agent_conversations(agent_id)"
        )
        conn.commit()
        print("Created agent_conversations table")


def _migrate_add_user_skills_table(conn):
    """Create user_skills table if it doesn't exist."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='user_skills'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL UNIQUE,
                skill_path TEXT NOT NULL,
                description TEXT,
                enabled INTEGER DEFAULT 1,
                selected_for_harness INTEGER DEFAULT 0,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_skills_enabled ON user_skills(enabled)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_skills_harness ON user_skills(selected_for_harness)"
        )
        conn.commit()
        print("Created user_skills table")


def _migrate_add_teams_products_projects_plugins(conn):
    """Create teams, products, projects, plugins tables if they don't exist."""
    tables_created = []

    # Teams table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='teams'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#00d4ff',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_teams_name ON teams(name)")
        tables_created.append("teams")

    # Team members table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='team_members'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'member',
                layer TEXT DEFAULT 'backend',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                UNIQUE(team_id, name)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)")
        tables_created.append("team_members")
    else:
        # Migrate existing team_members table to add missing columns
        cursor = conn.execute("PRAGMA table_info(team_members)")
        columns = {row[1] for row in cursor.fetchall()}
        if "description" not in columns:
            conn.execute("ALTER TABLE team_members ADD COLUMN description TEXT")
            tables_created.append("team_members (migrated description)")
        if "agent_id" not in columns:
            conn.execute("ALTER TABLE team_members ADD COLUMN agent_id TEXT REFERENCES agents(id)")
            tables_created.append("team_members (migrated agent_id)")
        if "super_agent_id" not in columns:
            conn.execute(
                "ALTER TABLE team_members ADD COLUMN super_agent_id TEXT"
                " REFERENCES super_agents(id)"
            )
            tables_created.append("team_members (migrated super_agent_id)")

    # Products table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'active',
                owner_team_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_team_id) REFERENCES teams(id) ON DELETE SET NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)")
        tables_created.append("products")

    # Projects table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'active',
                product_id TEXT,
                github_repo TEXT,
                owner_team_id TEXT,
                local_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
                FOREIGN KEY (owner_team_id) REFERENCES teams(id) ON DELETE SET NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_product ON projects(product_id)")
        tables_created.append("projects")
    else:
        # Add owner_team_id column if it doesn't exist (migration)
        cursor = conn.execute("PRAGMA table_info(projects)")
        columns = [row[1] for row in cursor.fetchall()]
        if "owner_team_id" not in columns:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN owner_team_id TEXT REFERENCES teams(id) ON DELETE SET NULL"
            )
            tables_created.append("projects (migrated owner_team_id)")

    # Project teams junction table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='project_teams'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                UNIQUE(project_id, team_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_teams_project ON project_teams(project_id)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_teams_team ON project_teams(team_id)")
        tables_created.append("project_teams")

    # Plugins table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='plugins'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plugins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                version TEXT DEFAULT '1.0.0',
                status TEXT DEFAULT 'draft',
                author TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_plugins_name ON plugins(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_plugins_status ON plugins(status)")
        tables_created.append("plugins")

    # Plugin components table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='plugin_components'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plugin_components_plugin ON plugin_components(plugin_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plugin_components_type ON plugin_components(type)"
        )
        tables_created.append("plugin_components")

    if tables_created:
        conn.commit()
        print(f"Created tables: {', '.join(tables_created)}")


def _migrate_webhook_fields(conn):
    """Ensure webhook configuration fields exist."""
    cursor = conn.execute("PRAGMA table_info(bots)")
    columns = {row[1] for row in cursor.fetchall()}

    added_columns = []

    # Add new columns for configurable webhook matching
    if "match_field_path" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN match_field_path TEXT")
        added_columns.append("match_field_path")

    if "match_field_value" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN match_field_value TEXT")
        added_columns.append("match_field_value")

    if "text_field_path" not in columns:
        conn.execute("ALTER TABLE bots ADD COLUMN text_field_path TEXT DEFAULT 'text'")
        added_columns.append("text_field_path")

    if added_columns:
        conn.commit()
        print(f"Added webhook columns: {', '.join(added_columns)}")

    # Migrate legacy bots to use new fields
    cursor = conn.execute(
        "SELECT id, group_id FROM bots WHERE trigger_source = 'agit' AND group_id > 0"
    )
    legacy_bots = cursor.fetchall()

    if legacy_bots:
        for bot in legacy_bots:
            conn.execute(
                """
                UPDATE bots
                SET match_field_path = 'event.group_id',
                    match_field_value = ?,
                    text_field_path = 'event.text',
                    trigger_source = 'webhook'
                WHERE id = ?
            """,
                (str(bot["group_id"]), bot["id"]),
            )
        conn.commit()
        print(f"Migrated {len(legacy_bots)} bots to webhook configuration")

    # Update any remaining legacy trigger sources to 'webhook'
    cursor = conn.execute(
        "UPDATE bots SET trigger_source = 'webhook' WHERE trigger_source = 'agit'"
    )
    if cursor.rowcount > 0:
        conn.commit()
        print(f"Updated {cursor.rowcount} bots to 'webhook' trigger source")


def _migrate_add_marketplaces_and_team_agents(conn):
    """Add marketplaces tables and agent references to teams."""
    tables_created = []
    columns_added = []

    # Create marketplaces table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='marketplaces'"
    )
    if not cursor.fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS marketplaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                type TEXT DEFAULT 'git',
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_marketplaces_name ON marketplaces(name)")
        tables_created.append("marketplaces")

    # Create marketplace_plugins junction table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='marketplace_plugins'"
    )
    if not cursor.fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS marketplace_plugins (
                id TEXT PRIMARY KEY,
                marketplace_id TEXT NOT NULL,
                plugin_id TEXT,
                remote_name TEXT,
                version TEXT,
                installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (marketplace_id) REFERENCES marketplaces(id) ON DELETE CASCADE,
                FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE SET NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_marketplace ON marketplace_plugins(marketplace_id)"
        )
        tables_created.append("marketplace_plugins")

    # Create settings table for key-value app settings
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        tables_created.append("settings")

    # Add leader_id column to teams table
    cursor = conn.execute("PRAGMA table_info(teams)")
    team_columns = {row[1] for row in cursor.fetchall()}
    if "leader_id" not in team_columns:
        conn.execute("ALTER TABLE teams ADD COLUMN leader_id TEXT REFERENCES agents(id)")
        columns_added.append("teams.leader_id")

    # Add agent_id column to team_members table
    cursor = conn.execute("PRAGMA table_info(team_members)")
    member_columns = {row[1] for row in cursor.fetchall()}
    if "agent_id" not in member_columns:
        conn.execute("ALTER TABLE team_members ADD COLUMN agent_id TEXT REFERENCES agents(id)")
        columns_added.append("team_members.agent_id")

    # Add project_id column to project_paths table for linking bots to projects
    cursor = conn.execute("PRAGMA table_info(project_paths)")
    path_columns = {row[1] for row in cursor.fetchall()}
    if "project_id" not in path_columns:
        conn.execute(
            "ALTER TABLE project_paths ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL"
        )
        columns_added.append("project_paths.project_id")

    if tables_created or columns_added:
        conn.commit()
        if tables_created:
            print(f"Created tables: {', '.join(tables_created)}")
        if columns_added:
            print(f"Added columns: {', '.join(columns_added)}")


def _migrate_add_hooks_commands_project_skills(conn):
    """Add hooks, commands, and project_skills tables."""
    tables_created = []
    columns_added = []

    # Create hooks table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hooks'")
    if not cursor.fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                event TEXT NOT NULL,
                description TEXT,
                content TEXT,
                enabled INTEGER DEFAULT 1,
                project_id TEXT,
                source_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hooks_project ON hooks(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hooks_event ON hooks(event)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hooks_enabled ON hooks(enabled)")
        tables_created.append("hooks")

    # Create commands table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='commands'")
    if not cursor.fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                content TEXT,
                arguments TEXT,
                enabled INTEGER DEFAULT 1,
                project_id TEXT,
                source_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commands_project ON commands(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commands_enabled ON commands(enabled)")
        tables_created.append("commands")

    # Create project_skills table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='project_skills'"
    )
    if not cursor.fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                skill_path TEXT,
                source TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, skill_name)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_skills_project ON project_skills(project_id)"
        )
        tables_created.append("project_skills")

    # Add layer column to agents table
    cursor = conn.execute("PRAGMA table_info(agents)")
    agent_columns = {row[1] for row in cursor.fetchall()}
    if "layer" not in agent_columns:
        conn.execute("ALTER TABLE agents ADD COLUMN layer TEXT")
        columns_added.append("agents.layer")
    if "detected_role" not in agent_columns:
        conn.execute("ALTER TABLE agents ADD COLUMN detected_role TEXT")
        columns_added.append("agents.detected_role")
    if "matched_skills" not in agent_columns:
        conn.execute("ALTER TABLE agents ADD COLUMN matched_skills TEXT")
        columns_added.append("agents.matched_skills")

    if tables_created or columns_added:
        conn.commit()
        if tables_created:
            print(f"Created tables: {', '.join(tables_created)}")
        if columns_added:
            print(f"Added columns: {', '.join(columns_added)}")


def _migrate_add_agent_effort_and_ai_backends(conn):
    """Add preferred_model/effort_level to agents and create AI backends tables."""
    columns_added = []
    tables_created = []
    data_migrated = []

    # Add new columns to agents table
    cursor = conn.execute("PRAGMA table_info(agents)")
    agent_columns = {row[1] for row in cursor.fetchall()}

    if "preferred_model" not in agent_columns:
        conn.execute("ALTER TABLE agents ADD COLUMN preferred_model TEXT")
        columns_added.append("agents.preferred_model")

    if "effort_level" not in agent_columns:
        conn.execute("ALTER TABLE agents ADD COLUMN effort_level TEXT DEFAULT 'medium'")
        columns_added.append("agents.effort_level")

    # Migrate team_members: remove 'senior' role (convert to 'member')
    cursor = conn.execute("SELECT COUNT(*) FROM team_members WHERE role = 'senior'")
    senior_count = cursor.fetchone()[0]
    if senior_count > 0:
        conn.execute("UPDATE team_members SET role = 'member' WHERE role = 'senior'")
        data_migrated.append(f"team_members: {senior_count} 'senior' roles -> 'member'")

    # Migrate deprecated layers: fullstack -> backend, devops -> maintenance
    cursor = conn.execute("SELECT COUNT(*) FROM team_members WHERE layer = 'fullstack'")
    fullstack_count = cursor.fetchone()[0]
    if fullstack_count > 0:
        conn.execute("UPDATE team_members SET layer = 'backend' WHERE layer = 'fullstack'")
        data_migrated.append(f"team_members: {fullstack_count} 'fullstack' layers -> 'backend'")

    cursor = conn.execute("SELECT COUNT(*) FROM team_members WHERE layer = 'devops'")
    devops_count = cursor.fetchone()[0]
    if devops_count > 0:
        conn.execute("UPDATE team_members SET layer = 'maintenance' WHERE layer = 'devops'")
        data_migrated.append(f"team_members: {devops_count} 'devops' layers -> 'maintenance'")

    # Create AI backends table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_backends'"
    )
    if cursor.fetchone() is None:
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
        tables_created.append("ai_backends")

        # Insert predefined backends
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
                """
                INSERT INTO ai_backends (id, name, type, description, icon, documentation_url, models)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                backend,
            )

    # Create backend accounts table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='backend_accounts'"
    )
    if cursor.fetchone() is None:
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (backend_id) REFERENCES ai_backends(id) ON DELETE CASCADE
            )
        """)
        tables_created.append("backend_accounts")

    if tables_created or columns_added or data_migrated:
        conn.commit()
        if tables_created:
            print(f"Created tables: {', '.join(tables_created)}")
        if columns_added:
            print(f"Added columns: {', '.join(columns_added)}")
        if data_migrated:
            print(f"Migrated data: {'; '.join(data_migrated)}")


def _migrate_update_backend_model_names(conn):
    """Update AI backend names and descriptions. Models are now discovered dynamically."""
    updates = [
        ("backend-claude", "Claude Code", "Anthropic's Claude AI assistant for coding"),
        ("backend-opencode", "OpenCode", "Open-source terminal coding assistant"),
        ("backend-gemini", "Gemini CLI", "Google's Gemini AI for coding"),
        ("backend-codex", "Codex CLI", "OpenAI's coding agent"),
    ]
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_backends'"
    )
    if cursor.fetchone() is None:
        return  # Table doesn't exist yet, nothing to update
    for bid, name, desc in updates:
        conn.execute(
            "UPDATE ai_backends SET name = ?, description = ? WHERE id = ?",
            (name, desc, bid),
        )


def _migrate_add_bot_config_snapshot(conn):
    """Add bot_config_snapshot column to execution_logs if missing."""
    cursor = conn.execute("PRAGMA table_info(execution_logs)")
    columns = {row[1] for row in cursor.fetchall()}
    if "bot_config_snapshot" not in columns:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN bot_config_snapshot TEXT")
        print("Added bot_config_snapshot column to execution_logs")


def _migrate_add_orchestration_tables(conn):
    """Add fallback_chains table and rate limit columns to backend_accounts and execution_logs."""
    tables_created = []
    columns_added = []

    # Create fallback_chains table if it doesn't exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fallback_chains'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fallback_chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                chain_order INTEGER NOT NULL,
                backend_type TEXT NOT NULL,
                account_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entity_id, chain_order)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fallback_chains_entity ON fallback_chains(entity_type, entity_id)"
        )
        tables_created.append("fallback_chains")

    # Add rate limit columns to backend_accounts
    cursor = conn.execute("PRAGMA table_info(backend_accounts)")
    account_columns = {row[1] for row in cursor.fetchall()}

    if "rate_limited_until" not in account_columns:
        conn.execute("ALTER TABLE backend_accounts ADD COLUMN rate_limited_until TIMESTAMP")
        columns_added.append("backend_accounts.rate_limited_until")

    if "rate_limit_reason" not in account_columns:
        conn.execute("ALTER TABLE backend_accounts ADD COLUMN rate_limit_reason TEXT")
        columns_added.append("backend_accounts.rate_limit_reason")

    if "last_used_at" not in account_columns:
        conn.execute("ALTER TABLE backend_accounts ADD COLUMN last_used_at TIMESTAMP")
        columns_added.append("backend_accounts.last_used_at")

    if "total_executions" not in account_columns:
        conn.execute("ALTER TABLE backend_accounts ADD COLUMN total_executions INTEGER DEFAULT 0")
        columns_added.append("backend_accounts.total_executions")

    if "email" not in account_columns:
        conn.execute("ALTER TABLE backend_accounts ADD COLUMN email TEXT")
        columns_added.append("backend_accounts.email")

    # Add last_used_at column to ai_backends
    cursor = conn.execute("PRAGMA table_info(ai_backends)")
    backend_columns = {row[1] for row in cursor.fetchall()}

    if "last_used_at" not in backend_columns:
        conn.execute("ALTER TABLE ai_backends ADD COLUMN last_used_at TIMESTAMP")
        # Seed from existing token_usage / execution_logs data
        conn.execute("""
            UPDATE ai_backends SET last_used_at = COALESCE(
                (SELECT MAX(tu.recorded_at) FROM token_usage tu WHERE tu.backend_type = ai_backends.type),
                (SELECT MAX(el.started_at) FROM execution_logs el WHERE el.backend_type = ai_backends.type)
            )
        """)
        # Also seed from conversation logs for backends without token_usage records
        conn.execute("""
            UPDATE ai_backends SET last_used_at = (
                SELECT MAX(json_extract(value, '$.timestamp'))
                FROM super_agent_sessions, json_each(conversation_log)
                WHERE json_extract(value, '$.backend') = ai_backends.type
                  AND json_extract(value, '$.timestamp') IS NOT NULL
            )
            WHERE last_used_at IS NULL
              AND EXISTS (
                SELECT 1 FROM super_agent_sessions, json_each(conversation_log)
                WHERE json_extract(value, '$.backend') = ai_backends.type
              )
        """)
        columns_added.append("ai_backends.last_used_at")

    # Add account_id column to execution_logs
    cursor = conn.execute("PRAGMA table_info(execution_logs)")
    exec_columns = {row[1] for row in cursor.fetchall()}

    if "account_id" not in exec_columns:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN account_id INTEGER")
        columns_added.append("execution_logs.account_id")

    if tables_created or columns_added:
        conn.commit()
        if tables_created:
            print(f"Created tables: {', '.join(tables_created)}")
        if columns_added:
            print(f"Added columns: {', '.join(columns_added)}")


def _migrate_add_budget_tables(conn):
    """Add token_usage and budget_limits tables, and token cache columns on execution_logs."""
    tables_created = []
    columns_added = []

    # Create token_usage table if it doesn't exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                backend_type TEXT NOT NULL,
                account_id INTEGER,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_creation_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0,
                num_turns INTEGER DEFAULT 0,
                duration_api_ms INTEGER DEFAULT 0,
                session_id TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_entity ON token_usage(entity_type, entity_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_recorded ON token_usage(recorded_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_execution ON token_usage(execution_id)"
        )
        tables_created.append("token_usage")

    # Create budget_limits table if it doesn't exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_limits'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budget_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                period TEXT NOT NULL DEFAULT 'monthly',
                soft_limit_usd REAL,
                hard_limit_usd REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entity_type, entity_id)
            )
        """)
        tables_created.append("budget_limits")

    # Add token cache columns to execution_logs
    cursor = conn.execute("PRAGMA table_info(execution_logs)")
    exec_columns = {row[1] for row in cursor.fetchall()}

    if "input_tokens" not in exec_columns:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN input_tokens INTEGER")
        columns_added.append("execution_logs.input_tokens")

    if "output_tokens" not in exec_columns:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN output_tokens INTEGER")
        columns_added.append("execution_logs.output_tokens")

    if "total_cost_usd" not in exec_columns:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN total_cost_usd REAL")
        columns_added.append("execution_logs.total_cost_usd")

    if tables_created or columns_added:
        conn.commit()
        if tables_created:
            print(f"Created budget tables: {', '.join(tables_created)}")
        if columns_added:
            print(f"Added budget columns: {', '.join(columns_added)}")


def _migrate_add_team_design_tables(conn):
    """Add topology/trigger columns to teams table and create team_agent_assignments table."""
    tables_created = []
    columns_added = []

    # Add new columns to teams table
    cursor = conn.execute("PRAGMA table_info(teams)")
    team_columns = {row[1] for row in cursor.fetchall()}

    if "topology" not in team_columns:
        conn.execute("ALTER TABLE teams ADD COLUMN topology TEXT DEFAULT NULL")
        columns_added.append("teams.topology")

    if "topology_config" not in team_columns:
        conn.execute("ALTER TABLE teams ADD COLUMN topology_config TEXT DEFAULT NULL")
        columns_added.append("teams.topology_config")

    if "trigger_source" not in team_columns:
        conn.execute("ALTER TABLE teams ADD COLUMN trigger_source TEXT DEFAULT NULL")
        columns_added.append("teams.trigger_source")

    if "trigger_config" not in team_columns:
        conn.execute("ALTER TABLE teams ADD COLUMN trigger_config TEXT DEFAULT NULL")
        columns_added.append("teams.trigger_config")

    if "enabled" not in team_columns:
        conn.execute("ALTER TABLE teams ADD COLUMN enabled INTEGER DEFAULT 1")
        columns_added.append("teams.enabled")

    # Create team_agent_assignments table if it doesn't exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='team_agent_assignments'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_agent_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
                UNIQUE(team_id, agent_id, entity_type, entity_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_taa_team ON team_agent_assignments(team_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_taa_agent ON team_agent_assignments(team_id, agent_id)"
        )
        tables_created.append("team_agent_assignments")

    if tables_created or columns_added:
        conn.commit()
        if tables_created:
            print(f"Created team design tables: {', '.join(tables_created)}")
        if columns_added:
            print(f"Added team design columns: {', '.join(columns_added)}")


def _migrate_add_design_conversations_table(conn):
    """Add design_conversations table for persisting conversation state."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='design_conversations'"
    )
    if cursor.fetchone() is None:
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
        conn.commit()
        print("Created design_conversations table")


def _migrate_add_sync_and_export_tables(conn):
    """Add sync_state and plugin_exports tables for plugin packaging."""
    tables_created = []

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_state'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content_hash TEXT,
                last_synced_at TIMESTAMP,
                sync_direction TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE CASCADE,
                UNIQUE(plugin_id, entity_type, entity_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_state_plugin ON sync_state(plugin_id)")
        tables_created.append("sync_state")

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='plugin_exports'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id TEXT NOT NULL,
                team_id TEXT,
                export_format TEXT NOT NULL,
                export_path TEXT,
                marketplace_id TEXT,
                version TEXT DEFAULT '1.0.0',
                status TEXT DEFAULT 'draft',
                last_exported_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE CASCADE,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL,
                FOREIGN KEY (marketplace_id) REFERENCES marketplaces(id) ON DELETE SET NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plugin_exports_plugin ON plugin_exports(plugin_id)"
        )
        tables_created.append("plugin_exports")

    if tables_created:
        conn.commit()
        print(f"Created plugin sync/export tables: {', '.join(tables_created)}")


def _migrate_add_project_local_path(conn):
    """Add local_path column to projects table for local directory-based projects."""
    cursor = conn.execute("PRAGMA table_info(projects)")
    columns = {row[1] for row in cursor.fetchall()}
    if "local_path" not in columns:
        conn.execute("ALTER TABLE projects ADD COLUMN local_path TEXT")
        conn.commit()
        print("Added local_path column to projects table")


def _migrate_add_rate_limit_snapshots(conn):
    """Add rate_limit_snapshots table for monitoring service."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rate_limit_snapshots'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                backend_type TEXT NOT NULL,
                window_type TEXT NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                tokens_limit INTEGER DEFAULT 0,
                percentage REAL DEFAULT 0.0,
                threshold_level TEXT DEFAULT 'normal',
                resets_at TIMESTAMP,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES backend_accounts(id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_account_time ON rate_limit_snapshots(account_id, recorded_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_time ON rate_limit_snapshots(recorded_at DESC)"
        )
        conn.commit()
        print("Created rate_limit_snapshots table")


def _migrate_add_agent_sessions(conn):
    """Add agent_sessions table for scheduler admission control."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_sessions'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'queued',
                stop_reason TEXT,
                stop_window_type TEXT,
                stop_eta_minutes REAL,
                resume_estimate TEXT,
                consecutive_safe_polls INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_sessions_state ON agent_sessions(state)")
        conn.commit()
        print("Created agent_sessions table")


def _migrate_bots_to_triggers(conn):
    """Migrate bots table to triggers table, bot_id columns to trigger_id."""
    # Idempotency check: if triggers table already exists, skip
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='triggers'")
    if cursor.fetchone():
        return  # Already migrated

    # Check if bots table exists (fresh install may not have it)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bots'")
    if not cursor.fetchone():
        return  # Fresh install, no migration needed

    logger.info("Migrating bots table to triggers...")

    # Record pre-migration row counts
    pre_bots = conn.execute("SELECT COUNT(*) FROM bots").fetchone()[0]
    pre_paths = conn.execute("SELECT COUNT(*) FROM project_paths").fetchone()[0]
    pre_logs = conn.execute("SELECT COUNT(*) FROM execution_logs").fetchone()[0]

    # Rename table
    conn.execute("ALTER TABLE bots RENAME TO triggers")

    # Rename columns in project_paths
    conn.execute("ALTER TABLE project_paths RENAME COLUMN bot_id TO trigger_id")

    # Rename columns in execution_logs
    conn.execute("ALTER TABLE execution_logs RENAME COLUMN bot_id TO trigger_id")
    conn.execute(
        "ALTER TABLE execution_logs RENAME COLUMN bot_config_snapshot TO trigger_config_snapshot"
    )

    # Rename columns in pr_reviews
    conn.execute("ALTER TABLE pr_reviews RENAME COLUMN bot_id TO trigger_id")

    # Update entity_type discriminators (wrap in try/except for fresh installs)
    try:
        conn.execute("UPDATE fallback_chains SET entity_type = 'trigger' WHERE entity_type = 'bot'")
    except Exception as e:
        logger.debug("Migration step: %s", e)
    try:
        conn.execute("UPDATE token_usage SET entity_type = 'trigger' WHERE entity_type = 'bot'")
    except Exception as e:
        logger.debug("Migration step: %s", e)
    try:
        conn.execute("UPDATE budget_limits SET entity_type = 'trigger' WHERE entity_type = 'bot'")
    except Exception as e:
        logger.debug("Migration step: %s", e)

    # Drop old indexes and create new ones
    conn.execute("DROP INDEX IF EXISTS idx_execution_logs_bot_id")
    conn.execute("DROP INDEX IF EXISTS idx_pr_reviews_bot_id")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_logs_trigger_id ON execution_logs(trigger_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_reviews_trigger_id ON pr_reviews(trigger_id)")

    # Verify post-migration row counts
    post_triggers = conn.execute("SELECT COUNT(*) FROM triggers").fetchone()[0]
    post_paths = conn.execute("SELECT COUNT(*) FROM project_paths").fetchone()[0]
    post_logs = conn.execute("SELECT COUNT(*) FROM execution_logs").fetchone()[0]

    assert (
        post_triggers == pre_bots
    ), f"Row count mismatch: triggers {post_triggers} != bots {pre_bots}"
    assert post_paths == pre_paths, f"Row count mismatch: project_paths {post_paths} != {pre_paths}"
    assert post_logs == pre_logs, f"Row count mismatch: execution_logs {post_logs} != {pre_logs}"

    # Run PRAGMA foreign_key_check and log violations
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        logger.warning(f"FK violations after migration: {violations}")

    # Verify FKs reference triggers table (not bots)
    for tbl in ("project_paths", "execution_logs", "pr_reviews"):
        fks = conn.execute(f"PRAGMA foreign_key_list({tbl})").fetchall()
        for fk in fks:
            if fk[2] == "bots":
                logger.warning(f"{tbl} FK still references bots: {fk}, rebuilding table...")
                _rebuild_table_fk(conn, tbl)
                break

    conn.commit()
    logger.info(
        f"Migration complete: {post_triggers} triggers, {post_paths} paths, {post_logs} logs"
    )


def _migrate_add_trigger_execution_mode(conn):
    """Add execution_mode and team_id columns to triggers table."""
    cursor = conn.execute("PRAGMA table_info(triggers)")
    columns = {row[1] for row in cursor.fetchall()}

    if "execution_mode" not in columns:
        conn.execute("ALTER TABLE triggers ADD COLUMN execution_mode TEXT DEFAULT 'direct'")
        print("Added execution_mode column to triggers")
    if "team_id" not in columns:
        conn.execute(
            "ALTER TABLE triggers ADD COLUMN team_id TEXT REFERENCES teams(id) ON DELETE SET NULL"
        )
        print("Added team_id column to triggers")

    conn.commit()


def _migrate_add_project_installations(conn):
    """Add project_installations table for tracking installed components."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='project_installations'"
    )
    if not cursor.fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_installations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                component_type TEXT NOT NULL,
                component_id TEXT NOT NULL,
                installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, component_type, component_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_installations_project "
            "ON project_installations(project_id)"
        )
        conn.commit()
        print("Created table: project_installations")


def _migrate_add_setup_executions(conn):
    """Add setup_executions table for interactive plugin setup audit trail."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='setup_executions'"
    )
    if not cursor.fetchone():
        conn.execute("""
            CREATE TABLE IF NOT EXISTS setup_executions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                command TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT NOT NULL,
                finished_at TEXT,
                exit_code INTEGER,
                error_message TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.commit()
        print("Created table: setup_executions")


def _migrate_drop_token_usage_fk(conn):
    """Drop FOREIGN KEY constraint on token_usage.execution_id so session imports work.

    SQLite doesn't support ALTER TABLE DROP CONSTRAINT, so we recreate the table.
    Also clears the imported-sessions tracker so they get re-imported.
    """
    cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='token_usage'")
    row = cursor.fetchone()
    if not row:
        return
    create_sql = row[0] or ""
    if "FOREIGN KEY" not in create_sql:
        return  # already clean

    print("Migrating token_usage: dropping FOREIGN KEY constraint...")
    conn.execute("ALTER TABLE token_usage RENAME TO token_usage_old")
    conn.execute("""
        CREATE TABLE token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            backend_type TEXT NOT NULL,
            account_id INTEGER,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            total_cost_usd REAL DEFAULT 0,
            num_turns INTEGER DEFAULT 0,
            duration_api_ms INTEGER DEFAULT 0,
            session_id TEXT,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO token_usage
        SELECT * FROM token_usage_old
    """)
    conn.execute("DROP TABLE token_usage_old")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_usage_entity ON token_usage(entity_type, entity_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_recorded ON token_usage(recorded_at)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_usage_execution ON token_usage(execution_id)"
    )

    # Clear imported-sessions tracking so they get re-imported into the clean table
    conn.execute("DELETE FROM settings WHERE key = 'session_usage_imported'")
    conn.commit()
    print("Migrated token_usage: FK dropped, imported sessions reset")


def _migrate_fix_session_recorded_at(conn):
    """Fix session recorded_at timestamps -- delete session records so they reimport
    with actual session timestamps instead of import time.

    One-time idempotent fix: only runs if session records exist with recorded_at
    matching today (i.e. recently bulk-imported with wrong timestamps).
    """
    cursor = conn.execute(
        "SELECT COUNT(*) as cnt FROM token_usage "
        "WHERE entity_type = 'session' AND date(recorded_at) = date('now')"
    )
    row = cursor.fetchone()
    if not row or row["cnt"] == 0:
        return  # No records to fix

    count = row["cnt"]
    conn.execute("DELETE FROM token_usage WHERE entity_type = 'session'")
    conn.execute("DELETE FROM settings WHERE key = 'session_usage_imported'")
    conn.commit()
    print(f"Reset {count} session records for timestamp fix (will reimport on next collection)")


# =============================================================================
# v0.3.0 migration functions
# =============================================================================


def _migrate_add_super_agents_tables(conn):
    """v0.3.0: Add SuperAgent entity tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS super_agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            backend_type TEXT NOT NULL DEFAULT 'claude',
            preferred_model TEXT,
            team_id TEXT,
            parent_super_agent_id TEXT,
            max_concurrent_sessions INTEGER DEFAULT 10,
            enabled INTEGER DEFAULT 1,
            config_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL,
            FOREIGN KEY (parent_super_agent_id) REFERENCES super_agents(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS super_agent_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            super_agent_id TEXT NOT NULL,
            doc_type TEXT NOT NULL CHECK(doc_type IN ('SOUL', 'IDENTITY', 'MEMORY', 'ROLE')),
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            version INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (super_agent_id) REFERENCES super_agents(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS super_agent_sessions (
            id TEXT PRIMARY KEY,
            super_agent_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'paused', 'completed', 'terminated')),
            conversation_log TEXT,
            summary TEXT,
            token_count INTEGER DEFAULT 0,
            last_compacted_at TIMESTAMP,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY (super_agent_id) REFERENCES super_agents(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id TEXT PRIMARY KEY,
            from_agent_id TEXT NOT NULL,
            to_agent_id TEXT,
            message_type TEXT NOT NULL DEFAULT 'message' CHECK(message_type IN ('message', 'broadcast', 'request', 'response', 'artifact', 'shutdown')),
            priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low', 'normal', 'high')),
            subject TEXT,
            content TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'delivered', 'read', 'expired')),
            ttl_seconds INTEGER,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TIMESTAMP,
            read_at TIMESTAMP,
            FOREIGN KEY (from_agent_id) REFERENCES super_agents(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_super_agent_docs_agent ON super_agent_documents(super_agent_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_super_agent_sessions_agent ON super_agent_sessions(super_agent_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_super_agent_sessions_status ON super_agent_sessions(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_to ON agent_messages(to_agent_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_from ON agent_messages(from_agent_id)"
    )


def _migrate_add_workflows_tables(conn):
    """v0.3.0: Add Workflow entity tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            trigger_type TEXT DEFAULT 'manual',
            trigger_config TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            graph_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
            UNIQUE(workflow_id, version)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_executions (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
            input_json TEXT,
            output_json TEXT,
            error TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_node_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            node_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
            input_json TEXT,
            output_json TEXT,
            error TEXT,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY (execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_versions_wf ON workflow_versions(workflow_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_executions_wf ON workflow_executions(workflow_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_node_execs_exec ON workflow_node_executions(execution_id)"
    )


def _migrate_add_sketches_table(conn):
    """v0.3.0: Add Sketch entity table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sketches (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'classified', 'routed', 'in_progress', 'completed', 'archived')),
            classification_json TEXT,
            routing_json TEXT,
            parent_sketch_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY (parent_sketch_id) REFERENCES sketches(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sketches_project ON sketches(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sketches_status ON sketches(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sketches_parent ON sketches(parent_sketch_id)")


def _migrate_add_proxy_columns(conn):
    """v0.3.0: Add CLIProxyAPI proxy_port and use_proxy columns to backend_accounts."""
    cursor = conn.execute("PRAGMA table_info(backend_accounts)")
    existing = {row[1] for row in cursor.fetchall()}

    if "proxy_port" not in existing:
        conn.execute("ALTER TABLE backend_accounts ADD COLUMN proxy_port INTEGER")
        logger.info("Added proxy_port column to backend_accounts")

    if "use_proxy" not in existing:
        conn.execute("ALTER TABLE backend_accounts ADD COLUMN use_proxy INTEGER DEFAULT 0")
        logger.info("Added use_proxy column to backend_accounts")


def _migrate_add_team_members_super_agent_id(conn):
    """v0.3.0: Add super_agent_id column to team_members for existing databases."""
    cursor = conn.execute("PRAGMA table_info(team_members)")
    columns = {row[1] for row in cursor.fetchall()}
    if "super_agent_id" not in columns:
        conn.execute(
            "ALTER TABLE team_members ADD COLUMN super_agent_id TEXT" " REFERENCES super_agents(id)"
        )
        logger.info("Added super_agent_id column to team_members")


def _migrate_add_team_edges_table(conn):
    """v0.3.0: Create team_edges table for existing databases."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='team_edges'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                source_member_id INTEGER NOT NULL,
                target_member_id INTEGER NOT NULL,
                edge_type TEXT NOT NULL DEFAULT 'delegation',
                label TEXT,
                weight INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY (source_member_id) REFERENCES team_members(id) ON DELETE CASCADE,
                FOREIGN KEY (target_member_id) REFERENCES team_members(id) ON DELETE CASCADE,
                CHECK (source_member_id != target_member_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_team_edges_team ON team_edges(team_id)")
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_team_edges_unique
            ON team_edges(team_id, source_member_id, target_member_id, edge_type)
        """)
        logger.info("Created team_edges table")


def _migrate_add_project_team_edges(conn):
    """v0.3.0: Add project_team_edges table and team_topology_config column."""
    # Add project_team_edges table
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='project_team_edges'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_team_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                source_team_id TEXT NOT NULL,
                target_team_id TEXT NOT NULL,
                edge_type TEXT NOT NULL DEFAULT 'dependency',
                label TEXT,
                weight INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (source_team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY (target_team_id) REFERENCES teams(id) ON DELETE CASCADE,
                CHECK (source_team_id != target_team_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_team_edges_project ON project_team_edges(project_id)"
        )
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_team_edges_unique
            ON project_team_edges(project_id, source_team_id, target_team_id, edge_type)
        """)
        logger.info("Created project_team_edges table")

    # Add team_topology_config column to projects
    cursor = conn.execute("PRAGMA table_info(projects)")
    columns = [row[1] for row in cursor.fetchall()]
    if "team_topology_config" not in columns:
        conn.execute("ALTER TABLE projects ADD COLUMN team_topology_config TEXT")
        logger.info("Added team_topology_config column to projects")


# =============================================================================
# v0.4.0 migrations
# =============================================================================


def _migrate_add_grd_tables(conn):
    """v0.4.0: Create GRD project management tables and extend projects table."""
    # milestones
    conn.execute("""
        CREATE TABLE IF NOT EXISTS milestones (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            version TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'planning'
                CHECK(status IN ('planning', 'active', 'completed', 'archived')),
            requirements_json TEXT,
            roadmap_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_milestones_status ON milestones(status)")

    # project_phases
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_phases (
            id TEXT PRIMARY KEY,
            milestone_id TEXT NOT NULL,
            phase_number INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            goal TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'active', 'completed', 'skipped')),
            dependencies TEXT,
            verification_level TEXT DEFAULT 'sanity',
            success_criteria TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (milestone_id) REFERENCES milestones(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_phases_milestone ON project_phases(milestone_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_phases_status ON project_phases(status)")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_project_phases_number ON project_phases(milestone_id, phase_number)"
    )

    # project_plans
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_plans (
            id TEXT PRIMARY KEY,
            phase_id TEXT NOT NULL,
            plan_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'in_review')),
            tasks_json TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (phase_id) REFERENCES project_phases(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_plans_phase ON project_plans(phase_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_plans_status ON project_plans(status)")

    # project_sessions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            phase_id TEXT,
            plan_id TEXT,
            agent_id TEXT,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active', 'paused', 'completed', 'failed')),
            summary TEXT,
            log_json TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (phase_id) REFERENCES project_phases(id) ON DELETE SET NULL,
            FOREIGN KEY (plan_id) REFERENCES project_plans(id) ON DELETE SET NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_sessions_project ON project_sessions(project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_sessions_status ON project_sessions(status)"
    )

    # project_sync_state
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_sync_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            content_hash TEXT,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, file_path)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_sync_project ON project_sync_state(project_id)"
    )

    # Extend projects table with GRD columns
    cursor = conn.execute("PRAGMA table_info(projects)")
    columns = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("grd_config", "TEXT"),
        ("grd_sync_hash", "TEXT"),
        ("grd_sync_at", "TIMESTAMP"),
        ("current_milestone_id", "TEXT"),
        ("worktree_base_path", "TEXT"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in columns:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_type}")
            logger.info("Added %s column to projects", col_name)


def _migrate_add_rotation_and_org_tables(conn):
    """v0.4.0: Create rotation events, team connections, product decisions, product milestones, milestone_projects tables."""
    # rotation_events
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rotation_events (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            from_account_id INTEGER,
            to_account_id INTEGER,
            reason TEXT,
            urgency TEXT DEFAULT 'normal'
                CHECK(urgency IN ('low', 'normal', 'high', 'critical')),
            utilization_at_rotation REAL,
            rotation_status TEXT NOT NULL DEFAULT 'pending'
                CHECK(rotation_status IN ('pending', 'completed', 'failed', 'skipped')),
            continuation_execution_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE,
            FOREIGN KEY (from_account_id) REFERENCES backend_accounts(id) ON DELETE SET NULL,
            FOREIGN KEY (to_account_id) REFERENCES backend_accounts(id) ON DELETE SET NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rotation_events_execution ON rotation_events(execution_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rotation_events_status ON rotation_events(rotation_status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rotation_events_created ON rotation_events(created_at DESC)"
    )

    # team_connections
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_team_id TEXT NOT NULL,
            target_team_id TEXT NOT NULL,
            connection_type TEXT NOT NULL DEFAULT 'dependency',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (target_team_id) REFERENCES teams(id) ON DELETE CASCADE,
            UNIQUE(source_team_id, target_team_id, connection_type),
            CHECK (source_team_id != target_team_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_connections_source ON team_connections(source_team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_connections_target ON team_connections(target_team_id)"
    )

    # product_decisions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_decisions (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            decision_type TEXT DEFAULT 'technical',
            status TEXT NOT NULL DEFAULT 'proposed'
                CHECK(status IN ('proposed', 'accepted', 'rejected', 'superseded')),
            decided_by TEXT,
            decided_at TIMESTAMP,
            context_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_decisions_product ON product_decisions(product_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_decisions_status ON product_decisions(status)"
    )

    # product_milestones
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_milestones (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            version TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'planning',
            target_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_milestones_product ON product_milestones(product_id)"
    )

    # milestone_projects
    conn.execute("""
        CREATE TABLE IF NOT EXISTS milestone_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            milestone_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            contribution TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (milestone_id) REFERENCES product_milestones(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(milestone_id, project_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_milestone_projects_milestone ON milestone_projects(milestone_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_milestone_projects_project ON milestone_projects(project_id)"
    )

    # Extend products table with owner_agent_id
    cursor = conn.execute("PRAGMA table_info(products)")
    columns = {row[1] for row in cursor.fetchall()}
    if "owner_agent_id" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN owner_agent_id TEXT")
        logger.info("Added owner_agent_id column to products")

    # Extend team_members table with tier
    cursor = conn.execute("PRAGMA table_info(team_members)")
    columns = {row[1] for row in cursor.fetchall()}
    if "tier" not in columns:
        conn.execute("ALTER TABLE team_members ADD COLUMN tier TEXT")
        logger.info("Added tier column to team_members")


def _migrate_add_mcp_and_handler_tables(conn):
    """v0.4.0: Create MCP server and execution type handler tables."""
    # mcp_servers
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mcp_servers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            server_type TEXT NOT NULL DEFAULT 'stdio',
            command TEXT,
            args TEXT,
            env_json TEXT,
            url TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_servers_name ON mcp_servers(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(enabled)")

    # project_mcp_servers
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_mcp_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            mcp_server_id TEXT NOT NULL,
            config_override TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (mcp_server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE,
            UNIQUE(project_id, mcp_server_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_mcp_project ON project_mcp_servers(project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_mcp_server ON project_mcp_servers(mcp_server_id)"
    )

    # execution_type_handlers
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_type_handlers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_type TEXT NOT NULL,
            handler_type TEXT NOT NULL,
            handler_config TEXT,
            priority INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(execution_type, handler_type)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eth_type ON execution_type_handlers(execution_type)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eth_enabled ON execution_type_handlers(enabled)")


def _migrate_add_in_review_plan_status(conn):
    """Recreate project_plans table to add 'in_review' to the CHECK constraint.

    SQLite CHECK constraints cannot be altered via ALTER TABLE, so we use the
    standard table recreation pattern: create new table, copy data, drop old,
    rename new, recreate indexes.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_plans'"
    ).fetchone()
    if not table_exists:
        return

    conn.execute("""
        CREATE TABLE _project_plans_new (
            id TEXT PRIMARY KEY,
            phase_id TEXT NOT NULL,
            plan_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'in_review')),
            tasks_json TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (phase_id) REFERENCES project_phases(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        INSERT INTO _project_plans_new
            (id, phase_id, plan_number, title, description, status,
             tasks_json, started_at, completed_at, created_at, updated_at)
        SELECT id, phase_id, plan_number, title, description, status,
               tasks_json, started_at, completed_at, created_at, updated_at
        FROM project_plans
    """)
    conn.execute("DROP TABLE project_plans")
    conn.execute("ALTER TABLE _project_plans_new RENAME TO project_plans")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_plans_phase ON project_plans(phase_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_plans_status ON project_plans(status)")


def _migrate_fix_in_review_check_constraint(conn):
    """Fix in_review CHECK constraint for DBs where v40 was previously a no-op."""
    sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='project_plans'"
    ).fetchone()
    if not sql_row or "in_review" in sql_row[0]:
        return  # Table doesn't exist or already has correct CHECK
    _migrate_add_in_review_plan_status(conn)


def _migrate_add_session_process_columns(conn):
    """v0.4.0: Add process tracking and worktree columns to project_sessions."""
    cursor = conn.execute("PRAGMA table_info(project_sessions)")
    columns = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("pid", "INTEGER"),
        ("pgid", "INTEGER"),
        ("worktree_path", "TEXT"),
        ("execution_type", "TEXT DEFAULT 'direct'"),
        ("execution_mode", "TEXT DEFAULT 'autonomous'"),
        ("idle_timeout_seconds", "INTEGER DEFAULT 3600"),
        ("max_lifetime_seconds", "INTEGER DEFAULT 14400"),
        ("last_activity_at", "TIMESTAMP"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in columns:
            conn.execute(f"ALTER TABLE project_sessions ADD COLUMN {col_name} {col_type}")
            logger.info("Added %s column to project_sessions", col_name)


def _migrate_v43_expand_mcp_schema(conn):
    """v0.4.0: Expand mcp_servers with preset catalog fields and project_mcp_servers with enable/env."""
    # Add columns to mcp_servers
    mcp_cols = [
        ("display_name", "TEXT"),
        ("category", "TEXT DEFAULT 'general'"),
        ("headers_json", "TEXT DEFAULT '{}'"),
        ("timeout_ms", "INTEGER DEFAULT 30000"),
        ("is_preset", "INTEGER DEFAULT 0"),
        ("icon", "TEXT"),
        ("documentation_url", "TEXT"),
        ("npm_package", "TEXT"),
    ]
    for col_name, col_def in mcp_cols:
        try:
            conn.execute(f"ALTER TABLE mcp_servers ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass  # Column already exists

    # Add columns to project_mcp_servers
    pms_cols = [
        ("enabled", "INTEGER DEFAULT 1"),
        ("env_overrides_json", "TEXT DEFAULT '{}'"),
    ]
    for col_name, col_def in pms_cols:
        try:
            conn.execute(f"ALTER TABLE project_mcp_servers ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass  # Column already exists

    # Backfill display_name from name where NULL
    conn.execute("UPDATE mcp_servers SET display_name = name WHERE display_name IS NULL")
    logger.info("Expanded mcp_servers and project_mcp_servers schema (v43)")


def _migrate_v44_product_owner_columns(conn):
    """v0.4.0: Add missing columns for product owner feature (Phase 52).

    - product_decisions: add rationale, tags_json; fix status enum (accepted -> approved)
    - product_milestones: add sort_order, progress_pct, completed_date
    """
    # --- product_decisions: add rationale and tags_json ---
    pd_cols = {row[1] for row in conn.execute("PRAGMA table_info(product_decisions)")}
    if "rationale" not in pd_cols:
        conn.execute("ALTER TABLE product_decisions ADD COLUMN rationale TEXT")
    if "tags_json" not in pd_cols:
        conn.execute("ALTER TABLE product_decisions ADD COLUMN tags_json TEXT DEFAULT '[]'")

    # --- product_decisions: fix status enum (accepted -> approved) ---
    # Check if table has any rows
    row_count = conn.execute("SELECT COUNT(*) FROM product_decisions").fetchone()[0]
    # Check if current CHECK uses 'accepted' by looking at table SQL
    table_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='product_decisions'"
    ).fetchone()
    table_sql = table_sql_row[0] if table_sql_row else ""

    if "'accepted'" in table_sql:
        # Need to recreate table with 'approved' instead of 'accepted'
        conn.execute("""
            CREATE TABLE product_decisions_new (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                rationale TEXT,
                tags_json TEXT DEFAULT '[]',
                decision_type TEXT DEFAULT 'technical',
                status TEXT NOT NULL DEFAULT 'proposed'
                    CHECK(status IN ('proposed', 'approved', 'rejected', 'superseded')),
                decided_by TEXT,
                decided_at TIMESTAMP,
                context_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)
        if row_count > 0:
            conn.execute("""
                INSERT INTO product_decisions_new
                (id, product_id, title, description, rationale, tags_json, decision_type,
                 status, decided_by, decided_at, context_json, created_at, updated_at)
                SELECT id, product_id, title, description, rationale, tags_json, decision_type,
                       CASE WHEN status = 'accepted' THEN 'approved' ELSE status END,
                       decided_by, decided_at, context_json, created_at, updated_at
                FROM product_decisions
            """)
        conn.execute("DROP TABLE product_decisions")
        conn.execute("ALTER TABLE product_decisions_new RENAME TO product_decisions")
        # Recreate indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_product_decisions_product ON product_decisions(product_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_product_decisions_status ON product_decisions(status)"
        )

    # --- product_milestones: add sort_order, progress_pct, completed_date ---
    pm_cols = {row[1] for row in conn.execute("PRAGMA table_info(product_milestones)")}
    if "sort_order" not in pm_cols:
        conn.execute("ALTER TABLE product_milestones ADD COLUMN sort_order INTEGER DEFAULT 0")
    if "progress_pct" not in pm_cols:
        conn.execute("ALTER TABLE product_milestones ADD COLUMN progress_pct INTEGER DEFAULT 0")
    if "completed_date" not in pm_cols:
        conn.execute("ALTER TABLE product_milestones ADD COLUMN completed_date TEXT")

    logger.info("Added product owner columns and fixed status enum (v44)")


# =============================================================================
# Preset MCP server definitions
# =============================================================================

PRESET_MCP_SERVERS = [
    {
        "name": "context7",
        "display_name": "Context7",
        "description": "Up-to-date code documentation for LLMs",
        "category": "documentation",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@upstash/context7-mcp"]',
        "env_json": "{}",
        "is_preset": 1,
        "icon": "book",
        "npm_package": "@upstash/context7-mcp",
        "documentation_url": "https://github.com/upstash/context7",
    },
    {
        "name": "playwright",
        "display_name": "Playwright",
        "description": "Browser automation via structured accessibility trees",
        "category": "testing",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@playwright/mcp@latest"]',
        "env_json": "{}",
        "is_preset": 1,
        "icon": "globe",
        "npm_package": "@playwright/mcp",
        "documentation_url": "https://github.com/microsoft/playwright-mcp",
    },
    {
        "name": "github",
        "display_name": "GitHub",
        "description": "GitHub API -- issues, PRs, repos, search",
        "category": "vcs",
        "server_type": "http",
        "command": None,
        "args": "[]",
        "env_json": "{}",
        "url": "https://api.githubcopilot.com/mcp/",
        "is_preset": 1,
        "icon": "git-branch",
        "npm_package": "@modelcontextprotocol/server-github",
        "documentation_url": "https://github.com/github/github-mcp-server",
    },
    {
        "name": "chrome-devtools",
        "display_name": "Chrome DevTools",
        "description": "Chrome DevTools for AI agents -- inspect, debug, profile",
        "category": "debugging",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "chrome-devtools-mcp@latest"]',
        "env_json": "{}",
        "is_preset": 1,
        "icon": "chrome",
        "npm_package": "chrome-devtools-mcp",
        "documentation_url": "https://github.com/nichochar/chrome-devtools-mcp",
    },
    {
        "name": "serena",
        "display_name": "Serena",
        "description": "Context-aware code refactoring engine",
        "category": "development",
        "server_type": "stdio",
        "command": "uvx",
        "args": '["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server"]',
        "env_json": "{}",
        "is_preset": 1,
        "icon": "code",
        "npm_package": None,
        "documentation_url": "https://github.com/oraios/serena",
    },
    {
        "name": "jira",
        "display_name": "Jira",
        "description": "Atlassian Jira -- issues, projects, JQL search",
        "category": "project-management",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@aashari/mcp-server-atlassian-jira"]',
        "env_json": '{"JIRA_URL": "", "JIRA_EMAIL": "", "JIRA_API_TOKEN": ""}',
        "is_preset": 1,
        "icon": "clipboard",
        "npm_package": "@aashari/mcp-server-atlassian-jira",
        "documentation_url": "https://github.com/aashari/mcp-server-atlassian-jira",
    },
    {
        "name": "linear",
        "display_name": "Linear",
        "description": "Linear issue tracking integration",
        "category": "project-management",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@mcp-devtools/linear"]',
        "env_json": '{"LINEAR_API_KEY": ""}',
        "is_preset": 1,
        "icon": "zap",
        "npm_package": "@mcp-devtools/linear",
        "documentation_url": "https://linear.app",
    },
    {
        "name": "slack",
        "display_name": "Slack",
        "description": "Slack workspace interaction -- channels, messages, users",
        "category": "communication",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@modelcontextprotocol/server-slack"]',
        "env_json": '{"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""}',
        "is_preset": 1,
        "icon": "message-square",
        "npm_package": "@modelcontextprotocol/server-slack",
        "documentation_url": "https://github.com/modelcontextprotocol/servers",
    },
    {
        "name": "telegram",
        "display_name": "Telegram",
        "description": "Telegram bot messaging and channel interaction",
        "category": "communication",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@iqai/mcp-telegram"]',
        "env_json": '{"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}',
        "is_preset": 1,
        "icon": "send",
        "npm_package": "@iqai/mcp-telegram",
        "documentation_url": "https://github.com/IQAIcom/mcp-telegram",
    },
]


def _migrate_v45_project_clone_fields(conn):
    """v0.4.0: Add clone_status, clone_error, last_synced_at to projects table."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    if "clone_status" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN clone_status TEXT DEFAULT 'none'")
    if "clone_error" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN clone_error TEXT")
    if "last_synced_at" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN last_synced_at TIMESTAMP")


# =============================================================================
# Versioned migration registry
# =============================================================================

VERSIONED_MIGRATIONS = [
    (1, "add_github_columns", _migrate_add_github_columns),
    (2, "add_pr_reviews_table", _migrate_add_pr_reviews_table),
    (3, "add_trigger_source", _migrate_add_trigger_source),
    (4, "add_schedule_columns", _migrate_add_schedule_columns),
    (5, "add_skill_command", _migrate_add_skill_command),
    (6, "add_model_column", _migrate_add_model_column),
    (7, "add_agents_tables", _migrate_add_agents_tables),
    (8, "add_user_skills_table", _migrate_add_user_skills_table),
    (9, "add_teams_products_projects_plugins", _migrate_add_teams_products_projects_plugins),
    (10, "webhook_fields", _migrate_webhook_fields),
    (11, "add_marketplaces_and_team_agents", _migrate_add_marketplaces_and_team_agents),
    (12, "add_hooks_commands_project_skills", _migrate_add_hooks_commands_project_skills),
    (13, "add_agent_effort_and_ai_backends", _migrate_add_agent_effort_and_ai_backends),
    (14, "update_backend_model_names", _migrate_update_backend_model_names),
    (15, "add_bot_config_snapshot", _migrate_add_bot_config_snapshot),
    (16, "add_orchestration_tables", _migrate_add_orchestration_tables),
    (17, "add_budget_tables", _migrate_add_budget_tables),
    (18, "add_team_design_tables", _migrate_add_team_design_tables),
    (19, "add_design_conversations_table", _migrate_add_design_conversations_table),
    (20, "add_sync_and_export_tables", _migrate_add_sync_and_export_tables),
    (21, "add_project_local_path", _migrate_add_project_local_path),
    (22, "add_rate_limit_snapshots", _migrate_add_rate_limit_snapshots),
    (23, "add_agent_sessions", _migrate_add_agent_sessions),
    (24, "bots_to_triggers", _migrate_bots_to_triggers),
    (25, "add_trigger_execution_mode", _migrate_add_trigger_execution_mode),
    (26, "add_project_installations", _migrate_add_project_installations),
    (27, "add_setup_executions", _migrate_add_setup_executions),
    (28, "drop_token_usage_fk", _migrate_drop_token_usage_fk),
    (29, "fix_session_recorded_at", _migrate_fix_session_recorded_at),
    # v0.3.0 migrations
    (30, "add_super_agents_tables", _migrate_add_super_agents_tables),
    (31, "add_workflows_tables", _migrate_add_workflows_tables),
    (32, "add_sketches_table", _migrate_add_sketches_table),
    (33, "add_proxy_columns", _migrate_add_proxy_columns),
    (34, "add_team_members_super_agent_id", _migrate_add_team_members_super_agent_id),
    (35, "add_team_edges_table", _migrate_add_team_edges_table),
    (36, "add_project_team_edges", _migrate_add_project_team_edges),
    # v0.4.0 migrations
    (37, "add_grd_tables", _migrate_add_grd_tables),
    (38, "add_rotation_and_org_tables", _migrate_add_rotation_and_org_tables),
    (39, "add_mcp_and_handler_tables", _migrate_add_mcp_and_handler_tables),
    (40, "add_in_review_plan_status", _migrate_add_in_review_plan_status),
    (41, "fix_in_review_check_constraint", _migrate_fix_in_review_check_constraint),
    (42, "add_session_process_columns", _migrate_add_session_process_columns),
    (43, "expand_mcp_schema", _migrate_v43_expand_mcp_schema),
    (44, "product_owner_columns", _migrate_v44_product_owner_columns),
    (45, "project_clone_fields", _migrate_v45_project_clone_fields),
]


# =============================================================================
# Seeding
# =============================================================================


def seed_predefined_triggers():
    """Insert all predefined triggers if they don't exist, or update if changed."""
    with get_connection() as conn:
        for trigger_def in PREDEFINED_TRIGGERS:
            cursor = conn.execute(
                "SELECT id, prompt_template, trigger_source, match_field_path, match_field_value, text_field_path FROM triggers WHERE id = ?",
                (trigger_def["id"],),
            )
            row = cursor.fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO triggers (id, name, group_id, detection_keyword, prompt_template, backend_type,
                                          trigger_source, match_field_path, match_field_value, text_field_path, is_predefined)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        trigger_def["id"],
                        trigger_def["name"],
                        trigger_def["group_id"],
                        trigger_def["detection_keyword"],
                        trigger_def["prompt_template"],
                        trigger_def["backend_type"],
                        trigger_def["trigger_source"],
                        trigger_def.get("match_field_path"),
                        trigger_def.get("match_field_value"),
                        trigger_def.get("text_field_path", "text"),
                        trigger_def["is_predefined"],
                    ),
                )
                print(f"Seeded predefined trigger: {trigger_def['name']} ({trigger_def['id']})")
            else:
                # Update if any configurable fields changed
                updates = []
                values = []
                if row["prompt_template"] != trigger_def["prompt_template"]:
                    updates.append("prompt_template = ?")
                    values.append(trigger_def["prompt_template"])
                if row["trigger_source"] != trigger_def["trigger_source"]:
                    updates.append("trigger_source = ?")
                    values.append(trigger_def["trigger_source"])
                if row["match_field_path"] != trigger_def.get("match_field_path"):
                    updates.append("match_field_path = ?")
                    values.append(trigger_def.get("match_field_path"))
                if row["match_field_value"] != trigger_def.get("match_field_value"):
                    updates.append("match_field_value = ?")
                    values.append(trigger_def.get("match_field_value"))
                if row["text_field_path"] != trigger_def.get("text_field_path", "text"):
                    updates.append("text_field_path = ?")
                    values.append(trigger_def.get("text_field_path", "text"))
                if updates:
                    values.append(trigger_def["id"])
                    conn.execute(f"UPDATE triggers SET {', '.join(updates)} WHERE id = ?", values)
                    print(f"Updated predefined trigger: {trigger_def['id']}")
        conn.commit()


def seed_preset_mcp_servers():
    """Insert/update preset MCP servers. Idempotent -- safe to call on every startup."""
    with get_connection() as conn:
        for preset in PRESET_MCP_SERVERS:
            existing = conn.execute(
                "SELECT id FROM mcp_servers WHERE name = ? AND is_preset = 1",
                (preset["name"],),
            ).fetchone()
            if existing:
                # Update existing preset to keep definitions current
                conn.execute(
                    """UPDATE mcp_servers SET
                        display_name=?, description=?, category=?, server_type=?,
                        command=?, args=?, env_json=?, url=?, icon=?,
                        npm_package=?, documentation_url=?, headers_json='{}',
                        timeout_ms=30000, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                    (
                        preset["display_name"],
                        preset["description"],
                        preset["category"],
                        preset["server_type"],
                        preset.get("command"),
                        preset.get("args", "[]"),
                        preset.get("env_json", "{}"),
                        preset.get("url"),
                        preset.get("icon"),
                        preset.get("npm_package"),
                        preset.get("documentation_url"),
                        existing["id"],
                    ),
                )
            else:
                # Insert new preset
                server_id = _get_unique_mcp_server_id(conn)
                conn.execute(
                    """INSERT INTO mcp_servers
                        (id, name, display_name, description, category, server_type,
                         command, args, env_json, url, is_preset, icon,
                         npm_package, documentation_url, headers_json, timeout_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, '{}', 30000)""",
                    (
                        server_id,
                        preset["name"],
                        preset["display_name"],
                        preset["description"],
                        preset["category"],
                        preset["server_type"],
                        preset.get("command"),
                        preset.get("args", "[]"),
                        preset.get("env_json", "{}"),
                        preset.get("url"),
                        preset.get("icon"),
                        preset.get("npm_package"),
                        preset.get("documentation_url"),
                    ),
                )
                logger.info("Seeded preset MCP server: %s (%s)", preset["display_name"], server_id)
        conn.commit()


# =============================================================================
# Path migration helpers
# =============================================================================


def migrate_existing_paths():
    """Create symlinks for any existing paths that don't have them."""
    # Import lazily to avoid circular dependency with database.py during transition
    from app.database import _create_symlink, _generate_symlink_name

    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, trigger_id, local_project_path FROM project_paths WHERE symlink_name IS NULL"
        )
        rows = cursor.fetchall()

        for row in rows:
            path_id = row["id"]
            trigger_id = row["trigger_id"]
            local_path = row["local_project_path"]

            # Generate and create symlink
            symlink_name = _generate_symlink_name(trigger_id, local_path)
            if _create_symlink(symlink_name, local_path):
                conn.execute(
                    "UPDATE project_paths SET symlink_name = ? WHERE id = ?",
                    (symlink_name, path_id),
                )
                print(f"Migrated path {local_path} -> {symlink_name}")

        conn.commit()


def auto_register_project_root():
    """Auto-register the project root directory for the predefined security trigger."""
    # Import lazily to avoid circular dependency with database.py during transition
    from app.database import _create_symlink, _generate_symlink_name, _remove_symlink

    with get_connection() as conn:
        # Check if predefined trigger exists
        cursor = conn.execute("SELECT id FROM triggers WHERE id = ?", (PREDEFINED_TRIGGER_ID,))
        if cursor.fetchone() is None:
            return  # Trigger doesn't exist yet

        # Check if project root is already registered
        cursor = conn.execute(
            "SELECT id FROM project_paths WHERE trigger_id = ? AND local_project_path = ?",
            (PREDEFINED_TRIGGER_ID, config.PROJECT_ROOT),
        )
        if cursor.fetchone() is not None:
            return  # Already registered

        # Register project root
        symlink_name = _generate_symlink_name(PREDEFINED_TRIGGER_ID, config.PROJECT_ROOT)
        if _create_symlink(symlink_name, config.PROJECT_ROOT):
            try:
                conn.execute(
                    "INSERT INTO project_paths (trigger_id, local_project_path, symlink_name) VALUES (?, ?, ?)",
                    (PREDEFINED_TRIGGER_ID, config.PROJECT_ROOT, symlink_name),
                )
                conn.commit()
                print(f"Auto-registered project root for security trigger: {config.PROJECT_ROOT}")
            except sqlite3.IntegrityError:
                _remove_symlink(symlink_name)
