"""Memory + embeddings DDL: chunked_executions, memory_threads/messages/embeddings,
working_memory, knowledge graph, consolidation, bot_memory."""

from ..connection import _is_pg


def _create_memory_messages_fts(conn):
    """SQLite-only FTS5 index + sync triggers for memory_messages semantic recall.

    Verbatim (byte-for-byte) copy of the DDL that lived inline in
    ``create_embedding_tables``; extracted so it can be skipped on Postgres (which
    has no FTS5) without re-indenting the SQLite path. On PG, recall degrades to
    an ILIKE scan over memory_messages (see app/db/agent_memory.py).
    """
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_messages_fts
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


def create_embedding_tables(conn):
    # Chunked executions (EXE-03: smart chunking with merge/dedup)
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

    # Chunk results (EXE-03: per-chunk bot output storage)
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

    # --- v0.4.0: Per-bot persistent memory store ---
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_memory_bot ON bot_memory(bot_id)")

    # --- Agent Memory tables ---
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

    # FTS5 virtual table for semantic recall (external content mode). FTS5 is
    # SQLite-only; on PG recall degrades to ILIKE over memory_messages, so the
    # virtual table + sync triggers are SQLite-only (kept verbatim in a helper so
    # the SQLite path is byte-for-byte unchanged).
    if not _is_pg():
        _create_memory_messages_fts(conn)

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

    # --- Memory Embeddings table ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            embedding BLOB NOT NULL,
            model TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
            dimension INTEGER NOT NULL DEFAULT 384,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(message_id, model)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_embeddings_message ON memory_embeddings(message_id)"
    )

    # --- Knowledge Graph tables ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kg_entities (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            name TEXT NOT NULL,
            entity_type TEXT NOT NULL DEFAULT 'concept',
            properties TEXT DEFAULT '{}',
            mention_count INTEGER DEFAULT 1,
            importance_score REAL DEFAULT 0.5,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(agent_id, name, entity_type)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_entities_agent ON kg_entities(agent_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kg_entities_agent_name ON kg_entities(agent_id, name)"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS kg_relations (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            properties TEXT DEFAULT '{}',
            confidence REAL DEFAULT 0.5,
            mention_count INTEGER DEFAULT 1,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_relations_source ON kg_relations(source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_relations_target ON kg_relations(target_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_relations_agent ON kg_relations(agent_id)")

    # --- Memory consolidation log ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_consolidation_log (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            thread_id TEXT,
            consolidation_type TEXT NOT NULL DEFAULT 'summary',
            summary TEXT,
            entity_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_consolidation_agent "
        "ON memory_consolidation_log(agent_id, created_at DESC)"
    )

    # --- KG extraction tracking ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kg_extraction_log (
            message_id TEXT PRIMARY KEY,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
