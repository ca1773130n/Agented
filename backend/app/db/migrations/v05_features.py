"""Migrations for v0.5.0 track — split out of migrations.py in v0.7.3c.

Function bodies are byte-identical copies from the original migrations.py.
"""

import logging

logger = logging.getLogger(__name__)


def _migrate_v52_trigger_sigterm_grace_seconds(conn):
    """Add sigterm_grace_seconds to triggers for per-trigger SIGTERM grace period config."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(triggers)")}
    if "sigterm_grace_seconds" not in cols:
        conn.execute("ALTER TABLE triggers ADD COLUMN sigterm_grace_seconds INTEGER")
        conn.commit()
        logger.info("Added sigterm_grace_seconds column to triggers")


def _migrate_v51_workflow_version_draft(conn):
    """Add is_draft column to workflow_versions for staging workflow changes."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(workflow_versions)")}
    if "is_draft" not in cols:
        conn.execute("ALTER TABLE workflow_versions ADD COLUMN is_draft INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        logger.info("Added is_draft column to workflow_versions")


def _migrate_v53_project_manager_super_agent(conn):
    """Add manager_super_agent_id to projects for AI-managed project chat."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    if "manager_super_agent_id" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN manager_super_agent_id TEXT")
        conn.commit()
        logger.info("Added manager_super_agent_id column to projects")


def _migrate_v54_project_grd_init_status(conn):
    """Add grd_init_status column to projects for GRD initialization tracking."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    if "grd_init_status" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN grd_init_status TEXT DEFAULT 'none'")
        conn.commit()
        logger.info("Added grd_init_status column to projects")


def _migrate_v47_webhook_dedup_keys(conn):
    """v0.4.0: Add webhook_dedup_keys table for DB-backed webhook deduplication."""
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


def _migrate_v56_add_workflow_approval_states(conn):
    """v0.2.0: Add workflow_approval_states table for approval gate persistence.

    Also updates CHECK constraints on workflow_executions and workflow_node_executions
    to include 'pending_approval' status.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_approval_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            timeout_seconds INTEGER DEFAULT 1800,
            requested_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT,
            UNIQUE(execution_id, node_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_approval_states_execution "
        "ON workflow_approval_states(execution_id)"
    )


def _migrate_v57_add_health_alerts_table(conn):
    """Add health_alerts table for bot health monitoring."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            trigger_id TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT,
            severity TEXT DEFAULT 'warning',
            acknowledged INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (trigger_id) REFERENCES triggers(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_health_alerts_trigger ON health_alerts(trigger_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_health_alerts_created ON health_alerts(created_at)"
    )


def _migrate_v58_budget_time_and_run_limits(conn):
    """Add max_execution_time_seconds and max_monthly_runs to budget_limits."""
    cursor = conn.execute("PRAGMA table_info(budget_limits)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if "max_execution_time_seconds" not in existing_cols:
        conn.execute("ALTER TABLE budget_limits ADD COLUMN max_execution_time_seconds INTEGER")
    if "max_monthly_runs" not in existing_cols:
        conn.execute("ALTER TABLE budget_limits ADD COLUMN max_monthly_runs INTEGER")


def _migrate_v57_add_rbac_and_audit_tables(conn):
    """Add user_roles table for RBAC and audit_events table for persistent audit trail."""
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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events(entity_type, entity_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON audit_events(actor)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at DESC)"
    )


def _migrate_v58_add_secrets_table(conn):
    """v0.2.0: Add secrets table for encrypted secrets vault."""
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


def _migrate_v59_add_bookmarks_table(conn):
    """Create bookmarks table for execution bookmarking with deep-links."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookmarks'")
    if cursor.fetchone() is None:
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookmarks_execution ON bookmarks(execution_id)"
        )
        conn.commit()
        logger.info("Created bookmarks table")


def _migrate_v60_add_integrations_table(conn):
    """v0.2.0: Add integrations table for external service adapters."""
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


def _migrate_v62_add_campaign_tables(conn):
    """Add campaigns and campaign_executions tables for multi-repo orchestration."""
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


# =============================================================================
# Versioned migration registry
# =============================================================================


def _migrate_v57_add_gitops_tables(conn):
    """Add gitops_repos and gitops_sync_log tables for GitOps sync engine."""
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
    conn.commit()


def _migrate_v63_add_replay_comparisons_table(conn):
    """Add replay_comparisons table for execution replay A/B comparison (EXE-01)."""
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
    conn.commit()


def _migrate_v64_add_conversation_branch_tables(conn):
    """Add conversation_messages and conversation_branches tables (EXE-04)."""
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
    conn.commit()


def _migrate_v65_add_chunk_tables(conn):
    """Add chunked_executions and chunk_results tables (EXE-03)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunked_executions (
            id TEXT PRIMARY KEY,
            bot_id TEXT NOT NULL,
            total_chunks INTEGER NOT NULL,
            completed_chunks INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            merged_output TEXT,
            unique_findings_count INTEGER,
            duplicate_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (bot_id) REFERENCES triggers(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunk_results (
            id TEXT PRIMARY KEY,
            chunked_execution_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_content TEXT NOT NULL,
            bot_output TEXT,
            token_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (chunked_execution_id) REFERENCES chunked_executions(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_results_exec ON chunk_results(chunked_execution_id)"
    )
    conn.commit()


def _migrate_v66_add_viewer_comments_table(conn):
    """Add viewer_comments table for inline commenting on execution log lines (EXE-05)."""
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
    conn.commit()


def _migrate_v69_bot_templates_table(conn):
    """Create bot_templates table for curated bot marketplace."""
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
    conn.commit()


def _migrate_v70_prompt_snippets_table(conn):
    """Create prompt_snippets table for reusable prompt fragments."""
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
    conn.commit()


def _migrate_v71_template_history_author_diff(conn):
    """Add author and diff_text columns to trigger_template_history."""
    try:
        conn.execute("ALTER TABLE trigger_template_history ADD COLUMN author TEXT DEFAULT 'system'")
    except Exception as e:
        logger.debug("trigger_template_history.author column already exists: %s", e)
    try:
        conn.execute("ALTER TABLE trigger_template_history ADD COLUMN diff_text TEXT DEFAULT ''")
    except Exception as e:
        logger.debug("trigger_template_history.diff_text column already exists: %s", e)
    conn.commit()


def _migrate_v72_add_execution_logs_fts(conn):
    """Add FTS5 virtual table and sync triggers for full-text search over execution logs."""
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

    # Rebuild the FTS index from existing execution_logs data
    conn.execute("""
        INSERT INTO execution_logs_fts(rowid, stdout_log, stderr_log, prompt)
        SELECT id, COALESCE(stdout_log, ''), COALESCE(stderr_log, ''), COALESCE(prompt, '')
        FROM execution_logs
    """)

    conn.commit()


def _migrate_v73_add_circuit_breakers_table(conn):
    """Add circuit_breakers table for per-backend resilience state persistence."""
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
    conn.commit()


def _migrate_v74_add_execution_queue_table(conn):
    """Add execution_queue table for durable dispatch with per-trigger concurrency."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_queue (
            id TEXT PRIMARY KEY,
            trigger_id TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            message_text TEXT,
            event_data TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            dispatched_at TEXT,
            completed_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eq_status ON execution_queue(status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eq_trigger_status ON execution_queue(trigger_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eq_priority_created "
        "ON execution_queue(priority DESC, created_at ASC)"
    )
    conn.commit()


def _migrate_v75_trigger_cron_expression(conn):
    """Add cron_expression column to triggers table for standard 5-field cron support."""
    try:
        conn.execute("ALTER TABLE triggers ADD COLUMN cron_expression TEXT")
        conn.commit()
    except Exception as e:
        logger.debug("triggers.cron_expression column already exists: %s", e)


def _migrate_76_super_agent_dispatch(conn):
    """Add dispatch_type and super_agent_id to triggers; session_id and source_type to execution_logs.

    Also drops NOT NULL constraint on execution_logs.trigger_id to support user_chat executions
    that have no associated trigger.
    """
    try:
        conn.execute("ALTER TABLE triggers ADD COLUMN dispatch_type TEXT DEFAULT 'bot'")
    except Exception as e:
        logger.debug("triggers.dispatch_type column already exists: %s", e)
    try:
        conn.execute("ALTER TABLE triggers ADD COLUMN super_agent_id TEXT")
    except Exception as e:
        logger.debug("triggers.super_agent_id column already exists: %s", e)
    try:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN session_id TEXT")
    except Exception as e:
        logger.debug("execution_logs.session_id column already exists: %s", e)
    try:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN source_type TEXT DEFAULT 'bot'")
    except Exception as e:
        logger.debug("execution_logs.source_type column already exists: %s", e)

    # Drop NOT NULL constraint on execution_logs.trigger_id so that user_chat executions
    # (which have no associated trigger) can be recorded. SQLite requires a full table
    # rebuild to change column constraints.
    cursor = conn.execute("PRAGMA table_info(execution_logs)")
    col_info = {row[1]: row for row in cursor.fetchall()}
    trigger_id_col = col_info.get("trigger_id")
    # row[3] is the notnull flag (1 = NOT NULL, 0 = nullable)
    if trigger_id_col and trigger_id_col[3] == 1:
        logger.info("Rebuilding execution_logs to drop NOT NULL on trigger_id")
        # Collect current column names preserving order
        cursor = conn.execute("PRAGMA table_info(execution_logs)")
        cols = [row[1] for row in cursor.fetchall()]
        cols_csv = ", ".join(cols)
        conn.execute("""
            CREATE TABLE execution_logs_new (
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
                session_id TEXT,
                source_type TEXT DEFAULT 'bot',
                FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            f"INSERT INTO execution_logs_new ({cols_csv}) SELECT {cols_csv} FROM execution_logs"
        )
        conn.execute("DROP TABLE execution_logs")
        conn.execute("ALTER TABLE execution_logs_new RENAME TO execution_logs")
        # Recreate indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_logs_trigger_id ON execution_logs(trigger_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_logs_started_at ON execution_logs(started_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_logs_status ON execution_logs(status)"
        )
        # Recreate FTS5 sync triggers (dropped with old table)
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


def _migrate_77_findings(conn):
    """Create findings table for the triage board (v0.4.0)."""
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
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status)")
    except Exception as e:
        logger.debug("idx_findings_status already exists: %s", e)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_bot_id ON findings(bot_id)")
    except Exception as e:
        logger.debug("idx_findings_bot_id already exists: %s", e)


def _migrate_78_bot_memory(conn):
    """Create bot_memory table for per-bot persistent key-value store (v0.4.0)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_memory (
            bot_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            expires_at TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bot_id, key)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_memory_bot ON bot_memory(bot_id)")
    except Exception as e:
        logger.debug("idx_bot_memory_bot already exists: %s", e)


def _migrate_79_execution_tags(conn):
    """Create execution_tags and execution_tag_assignments tables (v0.4.0)."""
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
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_eta_execution "
            "ON execution_tag_assignments(execution_id)"
        )
    except Exception as e:
        logger.debug("idx_eta_execution already exists: %s", e)


def _migrate_80_bot_pipes(conn):
    """Create bot_pipes and bot_pipe_executions tables for output piping (v0.4.0)."""
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
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bot_pipe_executions_pipe"
            " ON bot_pipe_executions(pipe_id)"
        )
    except Exception as e:
        logger.debug("idx_bot_pipe_executions_pipe already exists: %s", e)


def _migrate_84_pr_ownership_rules(conn):
    """Create pr_ownership_rules table for PR auto-assignment (v0.4.0)."""
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


def _migrate_81_add_retention_policies_table(conn):
    """Create retention_policies table for DataRetentionPoliciesPage (v0.4.0)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS retention_policies (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'global',
            scope_name TEXT NOT NULL DEFAULT 'All Teams',
            retention_days INTEGER NOT NULL DEFAULT 90,
            delete_on_expiry INTEGER NOT NULL DEFAULT 1,
            archive_on_expiry INTEGER NOT NULL DEFAULT 0,
            estimated_size_gb REAL NOT NULL DEFAULT 0.0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _migrate_83_onboarding_steps(conn):
    """Add onboarding_steps table for OnboardingAutomationPage."""
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


def _migrate_85_version_pins(conn):
    """Create version_pins and component_version_history tables."""
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
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vp_component_id ON version_pins(component_id)")
    except Exception as e:
        logger.debug("idx_vp_component_id already exists: %s", e)
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cvh_component_id"
            " ON component_version_history(component_id)"
        )
    except Exception as e:
        logger.debug("idx_cvh_component_id already exists: %s", e)
    conn.commit()


def _migrate_82_add_execution_quality_ratings(conn):
    """Add execution_quality_ratings table for AgentQualityScoringPage (v0.4.0)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_quality_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL UNIQUE,
            trigger_id TEXT,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            feedback TEXT DEFAULT '',
            rated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE SET NULL
        )
    """)
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_eqr_trigger_id ON execution_quality_ratings(trigger_id)"
        )
    except Exception as e:
        logger.debug("idx_eqr_trigger_id already exists: %s", e)
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_eqr_rated_at ON execution_quality_ratings(rated_at DESC)"
        )
    except Exception as e:
        logger.debug("idx_eqr_rated_at already exists: %s", e)


def _migrate_87_skill_sets_table(conn):
    """Add skill_sets table for VisualSkillComposerPage."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_sets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            skill_ids TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _migrate_86_scope_filters(conn):
    """Add scope_filters and scope_filter_patterns tables for RepoScopeFiltersPage."""
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


def _migrate_88_payload_transformers(conn):
    """Add payload_transformers table for WebhookPayloadTransformerPage (v0.4.0)."""
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
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_payload_transformers_trigger_id "
            "ON payload_transformers(trigger_id)"
        )
    except Exception as e:
        logger.debug("idx_payload_transformers_trigger_id already exists: %s", e)


def _migrate_add_super_agent_source(conn):
    """Add source column to super_agents table."""
    cursor = conn.execute("PRAGMA table_info(super_agents)")
    existing = {row[1] for row in cursor.fetchall()}
    if "source" not in existing:
        conn.execute("ALTER TABLE super_agents ADD COLUMN source TEXT DEFAULT 'ui_created'")
        conn.commit()


def _migrate_91_add_sketch_collaborating_status(conn):
    """Add 'collaborating' to sketches status CHECK constraint.

    SQLite CHECK constraints cannot be altered via ALTER TABLE, so we use the
    standard table recreation pattern: create new table, copy data, drop old,
    rename new, recreate indexes.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sketches'"
    ).fetchone()
    if not table_exists:
        return

    # Check if 'collaborating' is already in the constraint
    sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='sketches'"
    ).fetchone()
    if sql_row and "collaborating" in sql_row[0]:
        return  # Already has the correct constraint

    conn.execute("""
        CREATE TABLE _sketches_new (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft', 'classified', 'routed', 'in_progress', 'collaborating',
                                 'completed', 'archived')),
            classification_json TEXT,
            routing_json TEXT,
            parent_sketch_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY (parent_sketch_id) REFERENCES sketches(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
        INSERT INTO _sketches_new
            (id, title, content, project_id, status, classification_json,
             routing_json, parent_sketch_id, created_at, updated_at)
        SELECT id, title, content, project_id, status, classification_json,
               routing_json, parent_sketch_id, created_at, updated_at
        FROM sketches
    """)
    conn.execute("DROP TABLE sketches")
    conn.execute("ALTER TABLE _sketches_new RENAME TO sketches")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sketches_project ON sketches(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sketches_status ON sketches(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sketches_parent ON sketches(parent_sketch_id)")
    conn.commit()


def _migrate_92_system_errors_tables(conn):
    """Add system_errors and fix_attempts tables for error logging and autofix."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_errors (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source TEXT NOT NULL CHECK(source IN ('backend', 'frontend')),
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            stack_trace TEXT,
            request_id TEXT,
            context_json TEXT,
            error_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
                CHECK(status IN ('new', 'investigating', 'fixed', 'ignored')),
            fix_attempt_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_system_errors_status ON system_errors(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_system_errors_hash ON system_errors(error_hash)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_system_errors_timestamp ON system_errors(timestamp DESC)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fix_attempts (
            id TEXT PRIMARY KEY,
            error_id TEXT NOT NULL REFERENCES system_errors(id),
            tier INTEGER NOT NULL CHECK(tier IN (1, 2)),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'running', 'success', 'failed')),
            action_taken TEXT,
            agent_session_id TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fix_attempts_error_id ON fix_attempts(error_id)")


def _migrate_93_repair_health_alerts_table(conn):
    """Repair: create health_alerts if missing due to migration numbering collision.

    Migration 57 (health_alerts) could be skipped on DBs where version 57 was
    recorded as a different migration (rbac_and_audit_tables) due to a historical
    numbering mismatch. CREATE TABLE IF NOT EXISTS is safe to re-run.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            trigger_id TEXT,
            message TEXT NOT NULL,
            details TEXT,
            severity TEXT DEFAULT 'warning',
            acknowledged INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_health_alerts_trigger ON health_alerts(trigger_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_health_alerts_created ON health_alerts(created_at)"
    )


def _migrate_94_project_scoped_instances(conn):
    """Add project-scoped SA and team instance tables.

    1. Create project_sa_instances table
    2. Create project_team_instances table
    3. ALTER TABLE super_agent_sessions ADD COLUMN instance_id
    4. CREATE INDEX idx_sas_instance
    5. Data migration: create instance rows for existing sessions and project_teams
    """
    from ..ids import _get_unique_psa_id, _get_unique_pti_id

    # 1. Create project_sa_instances table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_sa_instances (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            template_sa_id TEXT NOT NULL REFERENCES super_agents(id),
            worktree_path TEXT,
            default_chat_mode TEXT NOT NULL DEFAULT 'management'
                CHECK(default_chat_mode IN ('management', 'work')),
            config_overrides TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, template_sa_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_psa_project ON project_sa_instances(project_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_psa_template ON project_sa_instances(template_sa_id)"
    )

    # 2. Create project_team_instances table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_team_instances (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            template_team_id TEXT NOT NULL REFERENCES teams(id),
            config_overrides TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, template_team_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pti_project ON project_team_instances(project_id)")

    # 3. ALTER TABLE super_agent_sessions ADD COLUMN instance_id
    try:
        conn.execute(
            "ALTER TABLE super_agent_sessions ADD COLUMN instance_id TEXT "
            "REFERENCES project_sa_instances(id) ON DELETE SET NULL"
        )
    except Exception:
        pass  # Column already exists

    # 4. CREATE INDEX on instance_id
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sas_instance ON super_agent_sessions(instance_id)")

    # 5. Data migration: create instance rows for existing relationships
    # 5a. For each SA with active sessions, find associated project and create instance
    active_sa_rows = conn.execute(
        "SELECT DISTINCT super_agent_id FROM super_agent_sessions WHERE status = 'active'"
    ).fetchall()
    for sa_row in active_sa_rows:
        sa_id = sa_row[0]

        # Try projects.manager_super_agent_id first
        proj_row = conn.execute(
            "SELECT id FROM projects WHERE manager_super_agent_id = ? LIMIT 1",
            (sa_id,),
        ).fetchone()

        if not proj_row:
            # Try project_teams -> team_members -> super_agent_id
            proj_row = conn.execute(
                """
                SELECT pt.project_id as id FROM project_teams pt
                JOIN team_members tm ON pt.team_id = tm.team_id
                WHERE tm.super_agent_id = ?
                LIMIT 1
                """,
                (sa_id,),
            ).fetchone()

        if not proj_row:
            # Fallback: first project
            proj_row = conn.execute(
                "SELECT id FROM projects ORDER BY created_at ASC LIMIT 1"
            ).fetchone()

        if proj_row:
            project_id = proj_row[0]
            # Check if instance already exists
            existing = conn.execute(
                "SELECT id FROM project_sa_instances WHERE project_id = ? AND template_sa_id = ?",
                (project_id, sa_id),
            ).fetchone()
            if not existing:
                psa_id = _get_unique_psa_id(conn)
                conn.execute(
                    """
                    INSERT INTO project_sa_instances
                    (id, project_id, template_sa_id)
                    VALUES (?, ?, ?)
                    """,
                    (psa_id, project_id, sa_id),
                )
            else:
                psa_id = existing[0]

            # Update sessions to point to this instance
            conn.execute(
                "UPDATE super_agent_sessions SET instance_id = ? "
                "WHERE super_agent_id = ? AND status = 'active'",
                (psa_id, sa_id),
            )

    # 5b. For each existing project_teams row, create project_team_instance
    # and project_sa_instance rows for SA members
    pt_rows = conn.execute("SELECT project_id, team_id FROM project_teams").fetchall()
    for pt_row in pt_rows:
        project_id = pt_row[0]
        team_id = pt_row[1]

        # Create project_team_instance if not exists
        existing_pti = conn.execute(
            "SELECT id FROM project_team_instances WHERE project_id = ? AND template_team_id = ?",
            (project_id, team_id),
        ).fetchone()
        if not existing_pti:
            pti_id = _get_unique_pti_id(conn)
            conn.execute(
                """
                INSERT INTO project_team_instances
                (id, project_id, template_team_id)
                VALUES (?, ?, ?)
                """,
                (pti_id, project_id, team_id),
            )

        # Create project_sa_instance for each SA member of this team
        sa_members = conn.execute(
            "SELECT super_agent_id FROM team_members "
            "WHERE team_id = ? AND super_agent_id IS NOT NULL",
            (team_id,),
        ).fetchall()
        for sa_member in sa_members:
            sa_id = sa_member[0]
            existing_psa = conn.execute(
                "SELECT id FROM project_sa_instances WHERE project_id = ? AND template_sa_id = ?",
                (project_id, sa_id),
            ).fetchone()
            if not existing_psa:
                psa_id = _get_unique_psa_id(conn)
                conn.execute(
                    """
                    INSERT INTO project_sa_instances
                    (id, project_id, template_sa_id)
                    VALUES (?, ?, ?)
                    """,
                    (psa_id, project_id, sa_id),
                )


def _migrate_95_trigger_conditions_and_budget_columns(conn):
    """Create trigger_conditions table and add missing budget_limits columns.

    trigger_conditions was defined in schema.py for fresh databases but had no
    migration for existing databases.

    budget_limits.max_execution_time_seconds and max_monthly_runs were originally
    in migration 58, but a version numbering conflict caused that migration to be
    skipped on databases that already had version 58 applied under a different name.
    """
    # --- trigger_conditions table ---
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trigger_conditions'"
    )
    if cursor.fetchone() is None:
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

    # --- budget_limits missing columns ---
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_limits'"
    )
    if cursor.fetchone() is not None:
        cursor = conn.execute("PRAGMA table_info(budget_limits)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "max_execution_time_seconds" not in existing_cols:
            conn.execute("ALTER TABLE budget_limits ADD COLUMN max_execution_time_seconds INTEGER")
        if "max_monthly_runs" not in existing_cols:
            conn.execute("ALTER TABLE budget_limits ADD COLUMN max_monthly_runs INTEGER")


def _migrate_96_app_meta(conn):
    """Create app_meta table with instance_id for DB-reset detection."""
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


def _migrate_97_agent_memory_tables(conn):
    """Create agent memory tables: memory_threads, memory_messages, FTS5, working memory."""
    # memory_threads
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_threads (
            id TEXT PRIMARY KEY,
            resource_id TEXT NOT NULL,
            resource_type TEXT NOT NULL DEFAULT 'agent',
            title TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_threads_resource "
        "ON memory_threads(resource_id, resource_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_threads_updated ON memory_threads(updated_at DESC)"
    )

    # memory_messages
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_messages (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL REFERENCES memory_threads(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'text',
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_messages_thread "
        "ON memory_messages(thread_id, created_at)"
    )

    # FTS5 virtual table for semantic recall
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_messages_fts'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE VIRTUAL TABLE memory_messages_fts
            USING fts5(
                content,
                content='memory_messages',
                content_rowid='rowid',
                tokenize='porter unicode61'
            )
        """)

    # Triggers to keep FTS index in sync
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_messages_ai AFTER INSERT ON memory_messages BEGIN
            INSERT INTO memory_messages_fts(rowid, content) VALUES (new.rowid, new.content);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_messages_ad AFTER DELETE ON memory_messages BEGIN
            INSERT INTO memory_messages_fts(memory_messages_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_messages_au AFTER UPDATE ON memory_messages BEGIN
            INSERT INTO memory_messages_fts(memory_messages_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
            INSERT INTO memory_messages_fts(rowid, content) VALUES (new.rowid, new.content);
        END
    """)

    # agent_working_memory
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_working_memory (
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL DEFAULT 'agent',
            content TEXT NOT NULL DEFAULT '',
            template TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (entity_id, entity_type)
        )
    """)

    # Add memory_config column to agents table
    cursor = conn.execute("PRAGMA table_info(agents)")
    columns = {row[1] for row in cursor.fetchall()}
    if "memory_config" not in columns:
        conn.execute("ALTER TABLE agents ADD COLUMN memory_config TEXT")
        logger.info("Added memory_config column to agents")


def _migrate_98_tracing_tables(conn):
    """Create structured tracing tables: traces and trace_spans."""
    tables_created = []

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='traces'")
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                execution_id TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                input TEXT,
                output TEXT,
                metadata TEXT,
                error_message TEXT,
                duration_ms INTEGER,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_traces_entity ON traces(entity_type, entity_id)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_execution ON traces(execution_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_started ON traces(started_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status)")
        tables_created.append("traces")

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trace_spans'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trace_spans (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                parent_span_id TEXT,
                name TEXT NOT NULL,
                span_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                input TEXT,
                output TEXT,
                attributes TEXT,
                metadata TEXT,
                error_message TEXT,
                duration_ms INTEGER,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                FOREIGN KEY (trace_id) REFERENCES traces(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_span_id) REFERENCES trace_spans(id) ON DELETE SET NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trace_spans_trace ON trace_spans(trace_id, started_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trace_spans_parent ON trace_spans(parent_span_id)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_spans_type ON trace_spans(span_type)")
        tables_created.append("trace_spans")

    if tables_created:
        conn.commit()
        logger.info("Created tracing tables: %s", ", ".join(tables_created))


def _migrate_99_kg_extraction_log(conn):
    """Add kg_extraction_log table for memory evolution tracking."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kg_extraction_log (
            message_id TEXT PRIMARY KEY,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _migrate_100_session_per_worktree(conn):
    """Add session-per-worktree columns to super_agent_sessions."""
    cursor = conn.execute("PRAGMA table_info(super_agent_sessions)")
    existing = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("worktree_path", "TEXT"),
        ("branch_name", "TEXT"),
        ("project_id", "TEXT REFERENCES projects(id) ON DELETE SET NULL"),
        ("title", "TEXT"),
        ("pr_url", "TEXT"),
        ("session_type", "TEXT NOT NULL DEFAULT 'worker'"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE super_agent_sessions ADD COLUMN {col_name} {col_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sas_project ON super_agent_sessions(project_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sas_session_type ON super_agent_sessions(session_type)"
    )


V05_MIGRATIONS = [
    (51, "workflow_version_draft", _migrate_v51_workflow_version_draft),
    (52, "trigger_sigterm_grace_seconds", _migrate_v52_trigger_sigterm_grace_seconds),
    (53, "project_manager_super_agent", _migrate_v53_project_manager_super_agent),
    (54, "project_grd_init_status", _migrate_v54_project_grd_init_status),
    (55, "webhook_dedup_keys", _migrate_v47_webhook_dedup_keys),
    # v0.2.0 migrations
    (56, "add_workflow_approval_states", _migrate_v56_add_workflow_approval_states),
    (57, "add_health_alerts_table", _migrate_v57_add_health_alerts_table),
    (58, "budget_time_and_run_limits", _migrate_v58_budget_time_and_run_limits),
    # v0.2.0 enterprise governance migrations
    (59, "add_rbac_and_audit_tables", _migrate_v57_add_rbac_and_audit_tables),
    (60, "add_secrets_table", _migrate_v58_add_secrets_table),
    (61, "add_bookmarks_table", _migrate_v59_add_bookmarks_table),
    (62, "add_integrations_table", _migrate_v60_add_integrations_table),
    (63, "add_gitops_tables", _migrate_v57_add_gitops_tables),
    (64, "add_campaign_tables", _migrate_v62_add_campaign_tables),
    (65, "add_replay_comparisons_table", _migrate_v63_add_replay_comparisons_table),
    (66, "add_conversation_branch_tables", _migrate_v64_add_conversation_branch_tables),
    (67, "add_chunk_tables", _migrate_v65_add_chunk_tables),
    (68, "add_viewer_comments_table", _migrate_v66_add_viewer_comments_table),
    (69, "bot_templates_table", _migrate_v69_bot_templates_table),
    (70, "prompt_snippets_table", _migrate_v70_prompt_snippets_table),
    (71, "template_history_author_diff", _migrate_v71_template_history_author_diff),
    (72, "add_execution_logs_fts", _migrate_v72_add_execution_logs_fts),
    # v0.2.0 resilience infrastructure
    (73, "add_circuit_breakers_table", _migrate_v73_add_circuit_breakers_table),
    (74, "add_execution_queue_table", _migrate_v74_add_execution_queue_table),
    # v0.2.0 API hardening
    (75, "trigger_cron_expression", _migrate_v75_trigger_cron_expression),
    # v0.4.0 core loop wiring
    (76, "super_agent_dispatch", _migrate_76_super_agent_dispatch),
    # v0.4.0 findings triage board
    (77, "findings", _migrate_77_findings),
    (78, "bot_memory", _migrate_78_bot_memory),
    (79, "execution_tags", _migrate_79_execution_tags),
    # v0.4.0 bot output piping
    (80, "bot_pipes", _migrate_80_bot_pipes),
    # v0.4.0 data retention policies
    (81, "add_retention_policies_table", _migrate_81_add_retention_policies_table),
    # v0.4.0 PR auto-assignment
    (84, "pr_ownership_rules", _migrate_84_pr_ownership_rules),
    # v0.4.0 visual skill composer
    (85, "version_pins", _migrate_85_version_pins),
    (82, "add_execution_quality_ratings", _migrate_82_add_execution_quality_ratings),
    (87, "skill_sets_table", _migrate_87_skill_sets_table),
    # v0.4.0 scope filters
    (86, "scope_filters", _migrate_86_scope_filters),
    # v0.4.0 onboarding automation
    (88, "onboarding_steps", _migrate_83_onboarding_steps),
    # v0.4.0 webhook payload transformer
    (89, "payload_transformers", _migrate_88_payload_transformers),
    (90, "add_super_agent_source", _migrate_add_super_agent_source),
    (91, "add_sketch_collaborating_status", _migrate_91_add_sketch_collaborating_status),
    (92, "system_errors_tables", _migrate_92_system_errors_tables),
    (93, "repair_health_alerts_table", _migrate_93_repair_health_alerts_table),
    # v0.5.0 project-scoped instances
    (94, "project_scoped_instances", _migrate_94_project_scoped_instances),
    # v0.5.0 fix: trigger_conditions table + budget_limits missing columns
    (
        95,
        "trigger_conditions_and_budget_columns",
        _migrate_95_trigger_conditions_and_budget_columns,
    ),
    # v0.5.0 onboarding — application metadata (instance tracking)
    (96, "app_meta_instance_id", _migrate_96_app_meta),
    # Agent memory system
    (97, "agent_memory_tables", _migrate_97_agent_memory_tables),
    # Structured tracing system
    (98, "tracing_tables", _migrate_98_tracing_tables),
    # KG extraction tracking for memory evolution
    (99, "kg_extraction_log", _migrate_99_kg_extraction_log),
    # v0.5.0 session-per-worktree
    (100, "session_per_worktree", _migrate_100_session_per_worktree),
]
