"""Workflow DDL: workflows, versions, executions, node executions, approvals, sketches."""


def create_workflow_tables(conn):
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
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'pending_approval')),
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
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'pending_approval')),
            input_json TEXT,
            output_json TEXT,
            error TEXT,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY (execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE
        )
    """)

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
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'classified', 'routed', 'in_progress', 'collaborating', 'completed', 'archived')),
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
