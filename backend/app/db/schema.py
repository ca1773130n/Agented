"""Fresh database schema creation for Agented.

Contains all CREATE TABLE and CREATE INDEX statements for a fresh database.
"""

import logging

logger = logging.getLogger(__name__)


def create_fresh_schema(conn):
    """Create all tables and indexes on a fresh (empty) database.

    This function contains the canonical schema definition. It is called by
    init_db() when no existing tables are detected.

    Args:
        conn: An open sqlite3 connection.
    """
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
            trigger_id TEXT NOT NULL,
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

    # Trigger template change history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trigger_template_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_id TEXT NOT NULL,
            old_template TEXT NOT NULL,
            new_template TEXT NOT NULL,
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

    # Agents table - AI agents with richer context than triggers
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
            layer TEXT,
            detected_role TEXT,
            matched_skills TEXT,
            preferred_model TEXT,
            effort_level TEXT DEFAULT 'medium',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_enabled ON agents(enabled)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_created_at ON agents(created_at DESC)")

    # Agent conversations table - for agent creation flow
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

    # User skills table - for skill management and harness integration
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

    # Teams table - for team management
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            color TEXT DEFAULT '#00d4ff',
            leader_id TEXT,
            source TEXT DEFAULT 'ui_created',
            topology TEXT DEFAULT NULL,
            topology_config TEXT DEFAULT NULL,
            trigger_source TEXT DEFAULT NULL,
            trigger_config TEXT DEFAULT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (leader_id) REFERENCES agents(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_teams_name ON teams(name)")

    # Team members table - members of teams (can reference agents or super_agents)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'member',
            layer TEXT DEFAULT 'backend',
            description TEXT,
            agent_id TEXT,
            super_agent_id TEXT,
            tier TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL,
            FOREIGN KEY (super_agent_id) REFERENCES super_agents(id) ON DELETE SET NULL,
            UNIQUE(team_id, name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)")

    # Team agent assignments table - skills/commands/hooks/rules per agent per team
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

    # Products table - for product management
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            owner_team_id TEXT,
            owner_agent_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_team_id) REFERENCES teams(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)")

    # Projects table - for project management
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            product_id TEXT,
            github_repo TEXT,
            github_host TEXT DEFAULT 'github.com',
            owner_team_id TEXT,
            local_path TEXT,
            team_topology_config TEXT,
            grd_config TEXT,
            grd_sync_hash TEXT,
            grd_sync_at TIMESTAMP,
            current_milestone_id TEXT,
            worktree_base_path TEXT,
            clone_status TEXT DEFAULT 'none',
            clone_error TEXT,
            last_synced_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
            FOREIGN KEY (owner_team_id) REFERENCES teams(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_product ON projects(product_id)")

    # Project teams junction table - teams assigned to projects
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

    # Project skills table - per-project skill associations
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

    # Fallback chains table - ordered fallback backends per trigger/agent
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

    # Token usage table - per-execution token data with entity linkage
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_recorded ON token_usage(recorded_at)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_usage_execution ON token_usage(execution_id)"
    )

    # Budget limits table - soft/hard spending limits per agent/team
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

    # Rate limit monitoring snapshots table
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

    # Agent scheduler sessions table
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

    # Settings table - key-value app settings
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # AI backends table - registered AI backend providers
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP
        )
    """)

    # Backend accounts table - per-backend account credentials and state
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
            proxy_port INTEGER,
            use_proxy INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (backend_id) REFERENCES ai_backends(id) ON DELETE CASCADE
        )
    """)

    # Design conversations table - for persisting conversation state
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

    # --- Schema version tracking ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- v0.3.0: SuperAgent tables ---
    # super_agents, super_agent_documents, super_agent_sessions, agent_messages

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

    # --- v0.3.0: Workflow tables ---
    # workflows, workflow_versions, workflow_executions, workflow_node_executions

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
            is_draft INTEGER NOT NULL DEFAULT 0,
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

    # --- v0.3.0: Sketch tables ---
    # sketches

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

    # --- v0.3.0: Team edges table (directed graph relationships) ---

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

    # --- v0.3.0: Project team edges table (org chart relationships) ---

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

    # --- v0.4.0: Project Execution & Autonomous Scheduling ---

    # milestones -- project-level milestones for GRD workflow
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

    # project_phases -- phases within a milestone
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

    # project_plans -- plans within a phase
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

    # project_sessions -- GRD execution sessions
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
            pid INTEGER,
            pgid INTEGER,
            worktree_path TEXT,
            execution_type TEXT DEFAULT 'direct',
            execution_mode TEXT DEFAULT 'autonomous',
            idle_timeout_seconds INTEGER DEFAULT 3600,
            max_lifetime_seconds INTEGER DEFAULT 14400,
            last_activity_at TIMESTAMP,
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

    # project_sync_state -- tracks file-to-entity mapping for GRD sync
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

    # rotation_events -- account rotation tracking during execution
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

    # team_connections -- directed relationships between teams
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

    # product_decisions -- decision records for products
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_decisions (
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_decisions_product ON product_decisions(product_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_decisions_status ON product_decisions(status)"
    )

    # product_milestones -- milestones at the product level
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_milestones (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            version TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'planning',
            target_date TEXT,
            sort_order INTEGER DEFAULT 0,
            progress_pct INTEGER DEFAULT 0 CHECK(progress_pct BETWEEN 0 AND 100),
            completed_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_milestones_product ON product_milestones(product_id)"
    )

    # milestone_projects -- junction: which projects contribute to a product milestone
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

    conn.commit()
