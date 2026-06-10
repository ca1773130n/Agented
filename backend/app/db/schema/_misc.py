"""Miscellaneous DDL — tables that don't cleanly fit any single domain.

Includes fallback chains, token usage, budgets, agent_sessions, settings, AI
backend registry, design conversations, schema_version, bookmarks,
integrations, GitOps repos, campaigns, replay/conversation branches,
viewer comments, execution queue, circuit breakers, findings, version
pins, app_meta, rotation_events.
"""


def create_misc_tables(conn):
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
            max_execution_time_seconds INTEGER,
            max_monthly_runs INTEGER,
            per_run_limit_usd REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(entity_type, entity_id)
        )
    """)

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

    # Chat retry queue — when every eligible account is rate-limited, a chat
    # turn is parked here and re-dispatched by the chat_retry_queue scheduler
    # job once any account's cooldown expires. One pending row per session
    # (UNIQUE) so a session can't pile up duplicate retries. Survives restarts.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_retry_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            super_agent_id TEXT NOT NULL,
            backend TEXT,
            account_id TEXT,
            model TEXT,
            cwd TEXT,
            chat_mode TEXT,
            instance_id TEXT,
            use_cli_agent INTEGER,
            attempts INTEGER DEFAULT 0,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_attempt_at TIMESTAMP
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

    # --- Bookmarks ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            trigger_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            notes TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            line_number INTEGER,
            deep_link TEXT NOT NULL,
            created_by TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_trigger ON bookmarks(trigger_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_execution ON bookmarks(execution_id)")

    # --- Integrations ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS integrations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            config TEXT NOT NULL DEFAULT '{}',
            trigger_id TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_integrations_type ON integrations(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_integrations_trigger ON integrations(trigger_id)")

    # --- v0.2.0: GitOps tables ---

    conn.execute("""
        CREATE TABLE IF NOT EXISTS gitops_repos (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            repo_url TEXT NOT NULL,
            branch TEXT NOT NULL DEFAULT 'main',
            config_path TEXT NOT NULL DEFAULT 'agented/',
            poll_interval_seconds INTEGER DEFAULT 60,
            last_sync_at TIMESTAMP,
            last_commit_sha TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS gitops_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id TEXT NOT NULL,
            commit_sha TEXT,
            files_changed INTEGER DEFAULT 0,
            files_applied INTEGER DEFAULT 0,
            files_conflicted INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (repo_id) REFERENCES gitops_repos(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gitops_sync_repo ON gitops_sync_log(repo_id)")

    # --- v0.2.0: Campaign tables (INT-07) ---

    conn.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            trigger_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            repo_urls TEXT NOT NULL,
            total_repos INTEGER DEFAULT 0,
            completed_repos INTEGER DEFAULT 0,
            failed_repos INTEGER DEFAULT 0,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_trigger ON campaigns(trigger_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS campaign_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL,
            execution_id TEXT,
            repo_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            error_message TEXT,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_campaign_exec_campaign ON campaign_executions(campaign_id)"
    )

    # Replay comparisons (EXE-01: execution replay and A/B comparison)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS replay_comparisons (
            id TEXT PRIMARY KEY,
            original_execution_id TEXT NOT NULL,
            replay_execution_id TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (original_execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE,
            FOREIGN KEY (replay_execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_replay_comp_original "
        "ON replay_comparisons(original_execution_id)"
    )

    # Conversation messages (EXE-04: tree-structured conversation branching)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            branch_id TEXT NOT NULL,
            parent_message_id TEXT,
            message_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conv_msg_conv_branch "
        "ON conversation_messages(conversation_id, branch_id)"
    )

    # Conversation branches (EXE-04: ContextBranch paper arXiv:2512.13914)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_branches (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            parent_branch_id TEXT,
            fork_message_id TEXT,
            name TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conv_branch_conv ON conversation_branches(conversation_id)"
    )

    # Viewer comments (EXE-05: inline comments on execution log lines)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS viewer_comments (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            viewer_id TEXT NOT NULL,
            viewer_name TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_viewer_comments_execution ON viewer_comments(execution_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_viewer_comments_execution_line "
        "ON viewer_comments(execution_id, line_number)"
    )

    # --- v0.2.0: Execution queue (durable dispatch with concurrency control) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_queue (
            id TEXT PRIMARY KEY,
            trigger_id TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            message_text TEXT,
            event_data TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            dispatched_at TEXT,
            completed_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eq_status ON execution_queue(status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eq_trigger_status ON execution_queue(trigger_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eq_priority_created ON execution_queue(priority DESC, created_at ASC)"
    )

    # --- v0.2.0: Circuit breakers (per-backend resilience) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS circuit_breakers (
            backend_type TEXT PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'closed',
            fail_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            last_failure_time REAL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # --- v0.4.0: Findings triage board ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS findings (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            bot_id TEXT,
            file_ref TEXT,
            owner TEXT,
            execution_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_bot_id ON findings(bot_id)")

    # --- v0.4.0: Skill and plugin version pinning ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS version_pins (
            id TEXT PRIMARY KEY,
            component_type TEXT NOT NULL,
            component_id TEXT NOT NULL,
            component_name TEXT NOT NULL,
            pinned_version TEXT,
            latest_version TEXT,
            bot_id TEXT,
            bot_name TEXT,
            status TEXT DEFAULT 'unpinned',
            pinned_at TEXT,
            changelog TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS component_version_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            component_id TEXT NOT NULL,
            version TEXT NOT NULL,
            released_at TEXT,
            breaking INTEGER DEFAULT 0,
            summary TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_component_id ON version_pins(component_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cvh_component_id ON component_version_history(component_id)"
    )

    # v0.5.0 onboarding — application metadata (instance tracking)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO app_meta (key, value) VALUES (
            'instance_id',
            lower(
                hex(randomblob(4)) || '-' ||
                hex(randomblob(2)) || '-4' ||
                substr(hex(randomblob(2)),2) || '-' ||
                substr('89ab', abs(random()) % 4 + 1, 1) ||
                substr(hex(randomblob(2)),2) || '-' ||
                hex(randomblob(6))
            )
        )
    """)
