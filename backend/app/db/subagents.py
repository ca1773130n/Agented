"""Subagent forge-primitive CRUD.

A ``subagent`` is a first-class forge primitive (mirroring rule/hook/command/
skill) whose ``content`` is the full ``.claude/agents/<name>.md`` body including
frontmatter. Rows use a ``subag-`` id prefix.

CRITICAL: this ``subagents`` table is entirely DISTINCT from the legacy
``agents`` table (used by ``HarnessLoaderService._import_agents`` via
``create_agent``). Do not conflate, reuse, or cross-wire the two.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from .connection import get_connection
from .ids import generate_subagent_id

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_subagent(
    name: str,
    content: str,
    description: Optional[str] = None,
    enabled: int = 1,
    project_id: Optional[str] = None,
    source_path: Optional[str] = None,
) -> dict:
    """Create a subagent. Returns the created row. Raises sqlite3.IntegrityError
    on duplicate name (UNIQUE constraint)."""
    subagent_id = generate_subagent_id()
    ts = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO subagents
                (id, name, description, content, enabled, project_id,
                 source_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subagent_id,
                name,
                description,
                content,
                enabled,
                project_id,
                source_path,
                ts,
                ts,
            ),
        )
        conn.commit()
    return get_subagent(subagent_id)


def get_subagent(subagent_id: str) -> Optional[dict]:
    """Get a single subagent by its ``subag-`` id."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM subagents WHERE id = ?", (subagent_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_subagent_by_name(name: str) -> Optional[dict]:
    """Get a subagent by its unique name."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM subagents WHERE name = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_subagents(project_id: Optional[str] = None) -> List[dict]:
    """List subagents, optionally scoped to a project."""
    with get_connection() as conn:
        if project_id is not None:
            cursor = conn.execute(
                "SELECT * FROM subagents WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
        else:
            cursor = conn.execute("SELECT * FROM subagents ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def update_subagent(subagent_id: str, **fields) -> bool:
    """Update a subagent's allowed fields. Returns True if a row changed."""
    allowed = {"name", "description", "content", "enabled", "project_id", "source_path"}
    updates = []
    values = []
    for key, value in fields.items():
        if key in allowed and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(_now())
    values.append(subagent_id)
    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE subagents SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_subagent(subagent_id: str) -> bool:
    """Delete a subagent. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM subagents WHERE id = ?", (subagent_id,))
        conn.commit()
        return cursor.rowcount > 0
