"""Setup-related DDL: setup_executions, bot_templates, bot_pipes, bot_pipe_executions."""


def create_setup_tables(conn):
    # Setup executions table (interactive plugin setup audit trail)
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

    # --- v0.2.0: Bot templates (TPL-01: curated bot marketplace) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_templates (
            id TEXT PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            icon TEXT DEFAULT '',
            config_json TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            source TEXT DEFAULT 'built-in',
            is_published INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_templates_slug ON bot_templates(slug)")

    # --- Bot output piping tables ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_pipes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_bot_id TEXT NOT NULL,
            dest_bot_id TEXT NOT NULL,
            transform TEXT NOT NULL DEFAULT 'passthrough',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_pipe_executions (
            id TEXT PRIMARY KEY,
            pipe_id TEXT NOT NULL REFERENCES bot_pipes(id) ON DELETE CASCADE,
            pipe_name TEXT NOT NULL,
            triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_preview TEXT,
            destination_status TEXT NOT NULL DEFAULT 'pending'
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bot_pipe_executions_pipe ON bot_pipe_executions(pipe_id)"
    )
