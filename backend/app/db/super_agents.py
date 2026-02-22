"""SuperAgent, Document, and Session CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_session_id, _get_unique_super_agent_id

logger = logging.getLogger(__name__)

# Valid document types (matches SQL CHECK constraint)
VALID_DOC_TYPES = {"SOUL", "IDENTITY", "MEMORY", "ROLE"}


# =============================================================================
# SuperAgent CRUD
# =============================================================================


def add_super_agent(
    name: str,
    description: str = None,
    backend_type: str = "claude",
    preferred_model: str = None,
    team_id: str = None,
    parent_super_agent_id: str = None,
    max_concurrent_sessions: int = 10,
    config_json: str = None,
) -> Optional[str]:
    """Add a new super agent. Returns super_agent_id on success, None on failure."""
    with get_connection() as conn:
        try:
            sa_id = _get_unique_super_agent_id(conn)
            conn.execute(
                """
                INSERT INTO super_agents
                (id, name, description, backend_type, preferred_model,
                 team_id, parent_super_agent_id, max_concurrent_sessions, config_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    sa_id,
                    name,
                    description,
                    backend_type,
                    preferred_model,
                    team_id,
                    parent_super_agent_id,
                    max_concurrent_sessions,
                    config_json,
                ),
            )
            conn.commit()
            return sa_id
        except sqlite3.IntegrityError:
            return None


def get_super_agent(super_agent_id: str) -> Optional[dict]:
    """Get a single super agent by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM super_agents WHERE id = ?", (super_agent_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_super_agents() -> List[dict]:
    """Get all super agents ordered by name."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM super_agents ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]


def update_super_agent(
    super_agent_id: str,
    name: str = None,
    description: str = None,
    backend_type: str = None,
    preferred_model: str = None,
    team_id: str = None,
    parent_super_agent_id: str = None,
    max_concurrent_sessions: int = None,
    enabled: int = None,
    config_json: str = None,
) -> bool:
    """Update super agent fields. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if backend_type is not None:
        updates.append("backend_type = ?")
        values.append(backend_type)
    if preferred_model is not None:
        updates.append("preferred_model = ?")
        values.append(preferred_model)
    if team_id is not None:
        updates.append("team_id = ?")
        values.append(team_id if team_id else None)
    if parent_super_agent_id is not None:
        updates.append("parent_super_agent_id = ?")
        values.append(parent_super_agent_id if parent_super_agent_id else None)
    if max_concurrent_sessions is not None:
        updates.append("max_concurrent_sessions = ?")
        values.append(max_concurrent_sessions)
    if enabled is not None:
        updates.append("enabled = ?")
        values.append(enabled)
    if config_json is not None:
        updates.append("config_json = ?")
        values.append(config_json)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(super_agent_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE super_agents SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_super_agent(super_agent_id: str) -> bool:
    """Delete a super agent. CASCADE handles documents and sessions. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM super_agents WHERE id = ?", (super_agent_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# SuperAgent Document CRUD
# =============================================================================


def add_super_agent_document(
    super_agent_id: str,
    doc_type: str,
    title: str,
    content: str = "",
) -> Optional[int]:
    """Add a document to a super agent. Returns document ID on success, None on failure."""
    if doc_type not in VALID_DOC_TYPES:
        return None
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO super_agent_documents
                (super_agent_id, doc_type, title, content)
                VALUES (?, ?, ?, ?)
            """,
                (super_agent_id, doc_type, title, content),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_super_agent_document(doc_id: int) -> Optional[dict]:
    """Get a single document by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM super_agent_documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_super_agent_documents(super_agent_id: str) -> List[dict]:
    """Get all documents for a super agent ordered by doc_type and title."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM super_agent_documents WHERE super_agent_id = ? ORDER BY doc_type ASC, title ASC",
            (super_agent_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_super_agent_document(doc_id: int, title: str = None, content: str = None) -> bool:
    """Update document fields. Increments version. Returns True on success."""
    updates = []
    values = []

    if title is not None:
        updates.append("title = ?")
        values.append(title)
    if content is not None:
        updates.append("content = ?")
        values.append(content)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    updates.append("version = version + 1")
    values.append(doc_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE super_agent_documents SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_super_agent_document(doc_id: int) -> bool:
    """Delete a document. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM super_agent_documents WHERE id = ?", (doc_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# SuperAgent Session CRUD
# =============================================================================


def add_super_agent_session(super_agent_id: str) -> Optional[str]:
    """Add a new session for a super agent. Returns session ID on success, None on failure."""
    with get_connection() as conn:
        try:
            sess_id = _get_unique_session_id(conn)
            conn.execute(
                """
                INSERT INTO super_agent_sessions
                (id, super_agent_id, status, conversation_log, token_count)
                VALUES (?, ?, 'active', '[]', 0)
            """,
                (sess_id, super_agent_id),
            )
            conn.commit()
            return sess_id
        except sqlite3.IntegrityError:
            return None


def get_super_agent_session(session_id: str) -> Optional[dict]:
    """Get a single session by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM super_agent_sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_super_agent_sessions(super_agent_id: str) -> List[dict]:
    """Get all sessions for a super agent ordered by started_at DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM super_agent_sessions WHERE super_agent_id = ? ORDER BY started_at DESC",
            (super_agent_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_super_agent_session(
    session_id: str,
    status: str = None,
    conversation_log: str = None,
    summary: str = None,
    token_count: int = None,
    last_compacted_at: str = None,
    ended_at: str = None,
) -> bool:
    """Update session fields. Returns True on success."""
    updates = []
    values = []

    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if conversation_log is not None:
        updates.append("conversation_log = ?")
        values.append(conversation_log)
    if summary is not None:
        updates.append("summary = ?")
        values.append(summary)
    if token_count is not None:
        updates.append("token_count = ?")
        values.append(token_count)
    if last_compacted_at is not None:
        updates.append("last_compacted_at = ?")
        values.append(last_compacted_at)
    if ended_at is not None:
        updates.append("ended_at = ?")
        values.append(ended_at)

    if not updates:
        return False

    values.append(session_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE super_agent_sessions SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_super_agent_session(session_id: str) -> bool:
    """Delete a session. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM super_agent_sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0


def count_active_sessions() -> int:
    """Count all active sessions across all super agents."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM super_agent_sessions WHERE status = 'active'")
        return cursor.fetchone()[0]


def get_active_sessions_list() -> List[dict]:
    """Get all active sessions ordered by started_at ASC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM super_agent_sessions WHERE status = 'active' ORDER BY started_at ASC"
        )
        return [dict(row) for row in cursor.fetchall()]
