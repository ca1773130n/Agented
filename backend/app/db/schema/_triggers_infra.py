"""Trigger infrastructure DDL: mcp_servers, project_mcp_servers, execution_type_handlers,
pending_retries, webhook_dedup_keys, trigger_conditions, onboarding_steps,
execution_tags, pr_ownership_rules, payload_transformers."""


def create_triggers_infra_tables(conn):
    # mcp_servers -- MCP server registry
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
            display_name TEXT,
            category TEXT DEFAULT 'general',
            headers_json TEXT DEFAULT '{}',
            timeout_ms INTEGER DEFAULT 30000,
            is_preset INTEGER DEFAULT 0,
            icon TEXT,
            documentation_url TEXT,
            npm_package TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_servers_name ON mcp_servers(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(enabled)")

    # project_mcp_servers -- junction: MCP servers assigned to projects
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_mcp_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            mcp_server_id TEXT NOT NULL,
            config_override TEXT,
            enabled INTEGER DEFAULT 1,
            env_overrides_json TEXT DEFAULT '{}',
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

    # execution_type_handlers -- maps execution types to handler configurations
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

    # Pending rate-limit retries - durable storage so retries survive server restarts
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_retries (
            trigger_id TEXT PRIMARY KEY,
            trigger_json TEXT NOT NULL,
            message_text TEXT NOT NULL DEFAULT '',
            event_json TEXT NOT NULL DEFAULT '{}',
            trigger_type TEXT NOT NULL DEFAULT 'webhook',
            cooldown_seconds INTEGER NOT NULL DEFAULT 0,
            retry_at TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Webhook deduplication keys ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_dedup_keys (
            trigger_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (trigger_id, payload_hash)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_webhook_dedup_created ON webhook_dedup_keys(created_at)"
    )

    # --- v0.4.0: Conditional trigger rules (filter conditions per trigger) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trigger_conditions (
            id TEXT PRIMARY KEY,
            trigger_id TEXT NOT NULL REFERENCES triggers(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            enabled INTEGER DEFAULT 1,
            logic TEXT NOT NULL DEFAULT 'AND',
            conditions_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tc_trigger ON trigger_conditions(trigger_id)")

    # --- Onboarding automation steps ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_steps (
            id TEXT PRIMARY KEY,
            trigger_id TEXT NOT NULL REFERENCES triggers(id) ON DELETE CASCADE,
            step_order INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'custom',
            enabled INTEGER NOT NULL DEFAULT 1,
            delay_minutes INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_onboarding_steps_trigger ON onboarding_steps(trigger_id)"
    )

    # --- Execution tags (tagging & full-text search feature) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_tags (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            color TEXT NOT NULL DEFAULT 'blue',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_tag_assignments (
            tag_id TEXT NOT NULL REFERENCES execution_tags(id) ON DELETE CASCADE,
            execution_id TEXT NOT NULL REFERENCES execution_logs(execution_id) ON DELETE CASCADE,
            PRIMARY KEY (tag_id, execution_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eta_execution ON execution_tag_assignments(execution_id)"
    )

    # --- v0.4.0: PR auto-assignment ownership rules ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pr_ownership_rules (
            id TEXT PRIMARY KEY,
            pattern TEXT NOT NULL,
            team TEXT NOT NULL,
            reviewers TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # --- v0.4.0: Webhook payload transformers ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payload_transformers (
            id TEXT PRIMARY KEY,
            trigger_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT 'default',
            rules TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_payload_transformers_trigger_id "
        "ON payload_transformers(trigger_id)"
    )
