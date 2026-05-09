"""Agents and agent_conversations DDL."""


def create_agent_tables(conn):
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
            memory_config TEXT,
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
