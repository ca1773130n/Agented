"""Core trigger / project_paths / execution_logs / prompt_snippets / pr_reviews DDL."""

from ..connection import _is_pg


def _create_execution_logs_fts(conn):
    """SQLite-only FTS5 index + sync triggers for execution_logs full-text search.

    Verbatim (byte-for-byte) copy of the DDL that lived inline in
    ``create_core_tables``; extracted so it can be skipped on Postgres (which has
    no FTS5) without re-indenting the SQLite path.
    """
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS execution_logs_fts
        USING fts5(
            stdout_log,
            stderr_log,
            prompt,
            content=execution_logs,
            content_rowid=id,
            tokenize='porter unicode61'
        )
    """)

    # Sync triggers to keep FTS5 index in sync with execution_logs
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS execution_logs_fts_insert
        AFTER INSERT ON execution_logs
        BEGIN
            INSERT INTO execution_logs_fts(rowid, stdout_log, stderr_log, prompt)
            VALUES (new.id, COALESCE(new.stdout_log, ''), COALESCE(new.stderr_log, ''), COALESCE(new.prompt, ''));
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS execution_logs_fts_update
        AFTER UPDATE OF stdout_log, stderr_log ON execution_logs
        BEGIN
            INSERT INTO execution_logs_fts(execution_logs_fts, rowid, stdout_log, stderr_log, prompt)
            VALUES ('delete', old.id, COALESCE(old.stdout_log, ''), COALESCE(old.stderr_log, ''), COALESCE(old.prompt, ''));
            INSERT INTO execution_logs_fts(rowid, stdout_log, stderr_log, prompt)
            VALUES (new.id, COALESCE(new.stdout_log, ''), COALESCE(new.stderr_log, ''), COALESCE(new.prompt, ''));
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS execution_logs_fts_delete
        AFTER DELETE ON execution_logs
        BEGIN
            INSERT INTO execution_logs_fts(execution_logs_fts, rowid, stdout_log, stderr_log, prompt)
            VALUES ('delete', old.id, COALESCE(old.stdout_log, ''), COALESCE(old.stderr_log, ''), COALESCE(old.prompt, ''));
        END
    """)


def create_core_tables(conn):
    # Triggers table with TEXT id
    conn.execute("""
        CREATE TABLE IF NOT EXISTS triggers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            group_id INTEGER NOT NULL DEFAULT 0,
            detection_keyword TEXT NOT NULL DEFAULT '',
            prompt_template TEXT NOT NULL,
            backend_type TEXT NOT NULL DEFAULT 'claude',
            trigger_source TEXT NOT NULL DEFAULT 'webhook',
            match_field_path TEXT,
            match_field_value TEXT,
            text_field_path TEXT DEFAULT 'text',
            is_predefined INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            auto_resolve INTEGER DEFAULT 0,
            auto_redispatch INTEGER DEFAULT 0,
            schedule_type TEXT,
            schedule_time TEXT,
            schedule_day INTEGER,
            schedule_timezone TEXT DEFAULT 'Asia/Seoul',
            next_run_at TIMESTAMP,
            last_run_at TIMESTAMP,
            skill_command TEXT,
            model TEXT,
            execution_mode TEXT DEFAULT 'direct',
            team_id TEXT REFERENCES teams(id) ON DELETE SET NULL,
            timeout_seconds INTEGER,
            webhook_secret TEXT,
            allowed_tools TEXT,
            sigterm_grace_seconds INTEGER,
            cron_expression TEXT,
            dispatch_type TEXT DEFAULT 'bot',
            super_agent_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Project paths table (linked to triggers with TEXT id)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_id TEXT NOT NULL,
            local_project_path TEXT NOT NULL,
            symlink_name TEXT,
            path_type TEXT NOT NULL DEFAULT 'local',
            github_repo_url TEXT,
            project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE CASCADE,
            UNIQUE(trigger_id, local_project_path)
        )
    """)

    # Execution logs table for trigger execution history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL UNIQUE,
            trigger_id TEXT,
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
            trigger_config_snapshot TEXT,
            account_id INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_cost_usd REAL,
            source_type TEXT DEFAULT 'bot',
            session_id TEXT,
            redispatched_from TEXT,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_logs_trigger_id ON execution_logs(trigger_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_logs_started_at ON execution_logs(started_at DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_logs_status ON execution_logs(status)")

    # FTS5 virtual table for full-text search over execution logs (BM25 ranking).
    # FTS5 is a SQLite-only extension with no Postgres analogue; on PG the
    # execution-log search degrades to an ILIKE scan over the execution_logs base
    # table (see ExecutionSearchService), so the virtual table + its sync triggers
    # are SQLite-only. The DDL strings are kept verbatim in a helper so the SQLite
    # path is byte-for-byte unchanged.
    if not _is_pg():
        _create_execution_logs_fts(conn)

    # Prompt snippets (reusable prompt fragments for {{snippet}} resolution)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompt_snippets (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_global INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_snippets_name ON prompt_snippets(name)"
    )

    # Trigger template change history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trigger_template_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_id TEXT NOT NULL,
            old_template TEXT NOT NULL,
            new_template TEXT NOT NULL,
            author TEXT DEFAULT 'system',
            diff_text TEXT DEFAULT '',
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trigger_template_history_trigger_id ON trigger_template_history(trigger_id)"
    )

    # PR review data table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pr_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_id TEXT NOT NULL DEFAULT 'bot-pr-review',
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
            FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_reviews_trigger_id ON pr_reviews(trigger_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_reviews_pr_status ON pr_reviews(pr_status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pr_reviews_review_status ON pr_reviews(review_status)"
    )
