"""SuperAgent DDL: super_agents, super_agent_documents, super_agent_sessions, agent_messages."""

from ..connection import _is_pg


def create_super_agent_tables(conn):
    # --- v0.3.0: SuperAgent tables ---
    # super_agents, super_agent_documents, super_agent_sessions, agent_messages

    # The super_agents cluster is created BEFORE the org cluster (teams/projects/
    # project_sa_instances) so that team_members/project_sa_instances can reference
    # super_agents — a true FK cycle. SQLite does not resolve FK *targets* at CREATE
    # TABLE time, so its DDL keeps these three edges inline (byte-for-byte
    # unchanged). Postgres DOES require the target relation to exist at CREATE time,
    # so on PG we omit these edges here and re-add them via ALTER TABLE in
    # ``add_super_agent_deferred_fks`` once every table exists.
    pg = _is_pg()
    team_fk = (
        "" if pg else "FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL,\n            "
    )
    instance_ref = "" if pg else " REFERENCES project_sa_instances(id) ON DELETE SET NULL"
    project_ref = "" if pg else " REFERENCES projects(id) ON DELETE SET NULL"

    conn.execute(f"""
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
            source TEXT DEFAULT 'ui_created',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            {team_fk}FOREIGN KEY (parent_super_agent_id) REFERENCES super_agents(id) ON DELETE SET NULL
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

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS super_agent_sessions (
            id TEXT PRIMARY KEY,
            super_agent_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'paused', 'completed', 'terminated')),
            conversation_log TEXT,
            summary TEXT,
            token_count INTEGER DEFAULT 0,
            last_compacted_at TIMESTAMP,
            instance_id TEXT{instance_ref},
            worktree_path TEXT,
            branch_name TEXT,
            project_id TEXT{project_ref},
            title TEXT,
            pr_url TEXT,
            session_type TEXT NOT NULL DEFAULT 'worker' CHECK(session_type IN ('leader', 'worker')),
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sas_instance ON super_agent_sessions(instance_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sas_project ON super_agent_sessions(project_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sas_session_type ON super_agent_sessions(session_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_to ON agent_messages(to_agent_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_from ON agent_messages(from_agent_id)"
    )


def add_super_agent_deferred_fks(conn):
    """Re-add the three forward-reference FKs stripped on Postgres (FK cycle).

    Called by ``create_fresh_schema`` on the Postgres path AFTER every table
    exists. Integrity-preserving: the same edges SQLite declares inline are
    materialised here as named constraints, so cross-table referential
    integrity is identical on both backends. No-op is impossible — this runs
    only on a fresh PG schema, where the constraints cannot yet exist.
    """
    conn.execute(
        "ALTER TABLE super_agents ADD CONSTRAINT super_agents_team_id_fkey "
        "FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL"
    )
    conn.execute(
        "ALTER TABLE super_agent_sessions ADD CONSTRAINT super_agent_sessions_instance_id_fkey "
        "FOREIGN KEY (instance_id) REFERENCES project_sa_instances(id) ON DELETE SET NULL"
    )
    conn.execute(
        "ALTER TABLE super_agent_sessions ADD CONSTRAINT super_agent_sessions_project_id_fkey "
        "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL"
    )
