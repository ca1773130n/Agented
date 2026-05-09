"""Plugin DDL: plugins, components, marketplaces, hooks/commands/rules, sync, exports."""


def create_plugin_tables(conn):
    # Plugins table - for plugin management
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

    # Plugin components table - components of plugins
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_plugin_components_type ON plugin_components(type)")

    # Marketplaces table - for plugin marketplace management
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

    # Marketplace plugins junction table
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

    # Hooks table - for hook management (global + per-project)
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

    # Commands table - for command management (global + per-project)
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

    # Rules table - for rule management (global + per-project)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            rule_type TEXT NOT NULL DEFAULT 'validation',
            condition TEXT,
            action TEXT,
            enabled INTEGER DEFAULT 1,
            project_id TEXT,
            source_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_project ON rules(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_type ON rules(rule_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_enabled ON rules(enabled)")

    # Project installations table - tracks which components are installed to which project
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
        "CREATE INDEX IF NOT EXISTS idx_project_installations_project ON project_installations(project_id)"
    )

    # Sync state table - tracks entity-to-file mapping for plugin sync
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

    # Plugin exports table - tracks export history
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
