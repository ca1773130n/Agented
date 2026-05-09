"""Monitoring DDL: rate_limit_snapshots, health_alerts, audit_events, retention,
quality_ratings, system_errors, fix_attempts, traces, trace_spans."""


def create_monitoring_tables(conn):
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

    # --- Health alerts table (v0.2.0: bot health monitoring) ---
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

    # audit_events -- persistent audit trail for all configuration changes
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

    # --- v0.4.0: Execution quality ratings ---
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eqr_trigger_id ON execution_quality_ratings(trigger_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eqr_rated_at ON execution_quality_ratings(rated_at DESC)"
    )

    # --- Retention policies ---
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

    # --- System error logging tables ---
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
            status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'investigating', 'fixed', 'ignored')),
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
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'success', 'failed')),
            action_taken TEXT,
            agent_session_id TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fix_attempts_error_id ON fix_attempts(error_id)")

    # --- Structured tracing tables ---
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_entity ON traces(entity_type, entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_execution ON traces(execution_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_started ON traces(started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status)")

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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_spans_parent ON trace_spans(parent_span_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_spans_type ON trace_spans(span_type)")
