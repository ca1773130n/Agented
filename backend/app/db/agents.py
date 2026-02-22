"""Agent CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_agent_id, _get_unique_conversation_id

logger = logging.getLogger(__name__)

# --- Constants ---

VALID_BACKENDS = ("claude", "opencode", "gemini", "codex")
VALID_AGENT_STATUSES = {"pending", "in_progress", "completed"}
VALID_EFFORT_LEVELS = {"low", "medium", "high", "max"}
VALID_CONVERSATION_STATUSES = {"active", "completed", "abandoned"}


# =============================================================================
# Agent CRUD
# =============================================================================


def add_agent(
    name: str,
    description: str = None,
    role: str = None,
    goals: str = None,
    context: str = None,
    backend_type: str = "claude",
    skills: str = None,
    documents: str = None,
    system_prompt: str = None,
    creation_conversation_id: str = None,
    creation_status: str = "completed",
    triggers: str = None,
    color: str = None,
    icon: str = None,
    model: str = None,
    temperature: float = None,
    tools: str = None,
    autonomous: int = 0,
    allowed_tools: str = None,
    layer: str = None,
    detected_role: str = None,
    matched_skills: str = None,
    preferred_model: str = None,
    effort_level: str = "medium",
) -> Optional[str]:
    """Add a new agent. Returns agent_id (string) on success, None on failure."""
    if backend_type not in VALID_BACKENDS:
        backend_type = "claude"
    if creation_status not in VALID_AGENT_STATUSES:
        creation_status = "completed"
    if effort_level not in VALID_EFFORT_LEVELS:
        effort_level = "medium"

    with get_connection() as conn:
        try:
            agent_id = _get_unique_agent_id(conn)
            conn.execute(
                """
                INSERT INTO agents (id, name, description, role, goals, context, backend_type,
                                    skills, documents, system_prompt, creation_conversation_id, creation_status,
                                    triggers, color, icon, model, temperature, tools, autonomous, allowed_tools,
                                    layer, detected_role, matched_skills, preferred_model, effort_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    agent_id,
                    name,
                    description,
                    role,
                    goals,
                    context,
                    backend_type,
                    skills,
                    documents,
                    system_prompt,
                    creation_conversation_id,
                    creation_status,
                    triggers,
                    color,
                    icon,
                    model,
                    temperature,
                    tools,
                    autonomous,
                    allowed_tools,
                    layer,
                    detected_role,
                    matched_skills,
                    preferred_model,
                    effort_level,
                ),
            )
            conn.commit()
            return agent_id
        except sqlite3.IntegrityError:
            return None


def update_agent(
    agent_id: str,
    name: str = None,
    description: str = None,
    role: str = None,
    goals: str = None,
    context: str = None,
    backend_type: str = None,
    enabled: int = None,
    skills: str = None,
    documents: str = None,
    system_prompt: str = None,
    creation_status: str = None,
    triggers: str = None,
    color: str = None,
    icon: str = None,
    model: str = None,
    temperature: float = None,
    tools: str = None,
    autonomous: int = None,
    allowed_tools: str = None,
    preferred_model: str = None,
    effort_level: str = None,
) -> bool:
    """Update agent fields. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if role is not None:
        updates.append("role = ?")
        values.append(role)
    if goals is not None:
        updates.append("goals = ?")
        values.append(goals)
    if context is not None:
        updates.append("context = ?")
        values.append(context)
    if backend_type is not None and backend_type in VALID_BACKENDS:
        updates.append("backend_type = ?")
        values.append(backend_type)
    if enabled is not None:
        updates.append("enabled = ?")
        values.append(enabled)
    if skills is not None:
        updates.append("skills = ?")
        values.append(skills)
    if documents is not None:
        updates.append("documents = ?")
        values.append(documents)
    if system_prompt is not None:
        updates.append("system_prompt = ?")
        values.append(system_prompt)
    if creation_status is not None and creation_status in VALID_AGENT_STATUSES:
        updates.append("creation_status = ?")
        values.append(creation_status)
    if triggers is not None:
        updates.append("triggers = ?")
        values.append(triggers)
    if color is not None:
        updates.append("color = ?")
        values.append(color)
    if icon is not None:
        updates.append("icon = ?")
        values.append(icon)
    if model is not None:
        updates.append("model = ?")
        values.append(model)
    if temperature is not None:
        updates.append("temperature = ?")
        values.append(temperature)
    if tools is not None:
        updates.append("tools = ?")
        values.append(tools)
    if autonomous is not None:
        updates.append("autonomous = ?")
        values.append(autonomous)
    if allowed_tools is not None:
        updates.append("allowed_tools = ?")
        values.append(allowed_tools)
    if preferred_model is not None:
        updates.append("preferred_model = ?")
        values.append(preferred_model)
    if effort_level is not None and effort_level in VALID_EFFORT_LEVELS:
        updates.append("effort_level = ?")
        values.append(effort_level)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(agent_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_agent(agent_id: str) -> bool:
    """Delete an agent. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_agent(agent_id: str) -> Optional[dict]:
    """Get a single agent by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_agent_by_name(name: str) -> Optional[dict]:
    """Get an agent by name."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM agents WHERE name = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_agents(limit: Optional[int] = None, offset: int = 0) -> List[dict]:
    """Get all agents with optional pagination."""
    with get_connection() as conn:
        sql = "SELECT * FROM agents ORDER BY created_at DESC"
        params: list = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_agents() -> int:
    """Count total number of agents."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM agents")
        return cursor.fetchone()[0]


def get_enabled_agents() -> List[dict]:
    """Get all enabled agents."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM agents WHERE enabled = 1 ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Agent conversation operations
# =============================================================================


def create_agent_conversation() -> str:
    """Create a new agent conversation. Returns conversation_id."""
    with get_connection() as conn:
        conv_id = _get_unique_conversation_id(conn)
        conn.execute(
            """
            INSERT INTO agent_conversations (id, status, messages)
            VALUES (?, 'active', '[]')
        """,
            (conv_id,),
        )
        conn.commit()
        return conv_id


def get_agent_conversation(conv_id: str) -> Optional[dict]:
    """Get a conversation by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM agent_conversations WHERE id = ?", (conv_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_agent_conversation(
    conv_id: str, agent_id: str = None, status: str = None, messages: str = None
) -> bool:
    """Update a conversation. Returns True on success."""
    updates = []
    values = []

    if agent_id is not None:
        updates.append("agent_id = ?")
        values.append(agent_id)
    if status is not None and status in VALID_CONVERSATION_STATUSES:
        updates.append("status = ?")
        values.append(status)
    if messages is not None:
        updates.append("messages = ?")
        values.append(messages)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(conv_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE agent_conversations SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_agent_conversation(conv_id: str) -> bool:
    """Delete a conversation. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM agent_conversations WHERE id = ?", (conv_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_active_conversations() -> List[dict]:
    """Get all active conversations."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM agent_conversations WHERE status = 'active' ORDER BY updated_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Design conversation operations
# =============================================================================


def create_design_conversation(conv_id: str, entity_type: str) -> bool:
    """Create a new design conversation record. Returns True on success."""
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO design_conversations (id, entity_type) VALUES (?, ?)",
                (conv_id, entity_type),
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Database error in create_design_conversation: {e}")
            return False


def get_design_conversation(conv_id: str) -> dict | None:
    """Get a design conversation by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, entity_type, entity_id, status, messages, config, created_at, updated_at "
            "FROM design_conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "entity_type": row[1],
            "entity_id": row[2],
            "status": row[3],
            "messages": row[4],
            "config": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }


def update_design_conversation(conv_id: str, **kwargs) -> bool:
    """Update a design conversation. Accepts: status, messages, config, entity_id."""
    updates = []
    values = []
    allowed = {"status", "messages", "config", "entity_id"}
    for key, val in kwargs.items():
        if key in allowed and val is not None:
            updates.append(f"{key} = ?")
            values.append(val)
    if not updates:
        return False
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(conv_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE design_conversations SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        conn.commit()
        return True


def list_design_conversations(entity_type: str, status: str = "active") -> list:
    """List design conversations by entity type and status."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, entity_type, entity_id, status, created_at, updated_at "
            "FROM design_conversations WHERE entity_type = ? AND status = ? "
            "ORDER BY updated_at DESC LIMIT 20",
            (entity_type, status),
        ).fetchall()
        return [
            {
                "id": r[0],
                "entity_type": r[1],
                "entity_id": r[2],
                "status": r[3],
                "created_at": r[4],
                "updated_at": r[5],
            }
            for r in rows
        ]


def delete_old_design_conversations(max_age_seconds: int = 86400) -> int:
    """Delete design conversations older than max_age_seconds. Returns count deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM design_conversations WHERE status != 'active' "
            "AND updated_at < datetime('now', ?)",
            (f"-{max_age_seconds} seconds",),
        )
        conn.commit()
        return cursor.rowcount
