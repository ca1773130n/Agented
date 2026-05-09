"""Security DDL: user_roles, secrets, scope_filters."""


def create_security_tables(conn):
    # user_roles -- RBAC role assignments mapped to API keys
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            id TEXT PRIMARY KEY,
            api_key TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'viewer'
                CHECK(role IN ('viewer', 'operator', 'editor', 'admin')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_api_key ON user_roles(api_key)")

    # --- v0.2.0: Secrets vault ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS secrets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            encrypted_value TEXT NOT NULL,
            description TEXT DEFAULT '',
            scope TEXT DEFAULT 'global',
            created_by TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_secrets_name ON secrets(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_secrets_scope ON secrets(scope)")

    # --- Scope filters tables ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scope_filters (
            id TEXT PRIMARY KEY,
            trigger_id TEXT NOT NULL UNIQUE REFERENCES triggers(id) ON DELETE CASCADE,
            mode TEXT NOT NULL DEFAULT 'denylist',
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scope_filter_patterns (
            id TEXT PRIMARY KEY,
            filter_id TEXT NOT NULL REFERENCES scope_filters(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sfp_filter ON scope_filter_patterns(filter_id)")
