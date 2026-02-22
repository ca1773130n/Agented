"""MCP server and execution type handler CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_mcp_server_id

logger = logging.getLogger(__name__)


# =============================================================================
# MCP Server CRUD
# =============================================================================


def add_mcp_server(
    name: str,
    description: str = None,
    server_type: str = "stdio",
    command: str = None,
    args: str = None,
    env_json: str = None,
    url: str = None,
    display_name: str = None,
    category: str = "general",
    headers_json: str = None,
    timeout_ms: int = 30000,
    is_preset: int = 0,
    icon: str = None,
    documentation_url: str = None,
    npm_package: str = None,
) -> Optional[str]:
    """Add a new MCP server. Returns server_id on success, None on failure.

    Uses dynamic column building to only include non-None fields.
    """
    with get_connection() as conn:
        try:
            server_id = _get_unique_mcp_server_id(conn)
            # Required columns
            columns = ["id", "name"]
            values = [server_id, name]
            # Optional columns -- only include when provided
            optional = {
                "description": description,
                "server_type": server_type,
                "command": command,
                "args": args,
                "env_json": env_json,
                "url": url,
                "display_name": display_name,
                "category": category,
                "headers_json": headers_json,
                "timeout_ms": timeout_ms,
                "is_preset": is_preset,
                "icon": icon,
                "documentation_url": documentation_url,
                "npm_package": npm_package,
            }
            for col, val in optional.items():
                if val is not None:
                    columns.append(col)
                    values.append(val)

            placeholders = ", ".join("?" for _ in values)
            col_str = ", ".join(columns)
            conn.execute(
                f"INSERT INTO mcp_servers ({col_str}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
            return server_id
        except sqlite3.IntegrityError:
            return None


def get_mcp_server(server_id: str) -> Optional[dict]:
    """Get a single MCP server by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_mcp_servers(limit: Optional[int] = None, offset: int = 0) -> List[dict]:
    """Get all MCP servers with optional pagination."""
    with get_connection() as conn:
        sql = "SELECT * FROM mcp_servers ORDER BY name ASC"
        params: list = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_mcp_servers() -> int:
    """Count total number of MCP servers."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM mcp_servers")
        return cursor.fetchone()[0]


def update_mcp_server(server_id: str, **kwargs) -> bool:
    """Update MCP server fields. Returns True on success.

    Supported kwargs: name, description, server_type, command, args, env_json,
    url, enabled, display_name, category, headers_json, timeout_ms, is_preset,
    icon, documentation_url, npm_package.
    """
    allowed = {
        "name",
        "description",
        "server_type",
        "command",
        "args",
        "env_json",
        "url",
        "enabled",
        "display_name",
        "category",
        "headers_json",
        "timeout_ms",
        "is_preset",
        "icon",
        "documentation_url",
        "npm_package",
    }
    updates = []
    values = []

    for key, value in kwargs.items():
        if key in allowed and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(server_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE mcp_servers SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_mcp_server(server_id: str) -> bool:
    """Delete an MCP server. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Project MCP Server CRUD
# =============================================================================


def assign_mcp_to_project(
    project_id: str,
    mcp_server_id: str,
    config_override: str = None,
    env_overrides_json: str = None,
) -> Optional[int]:
    """Assign an MCP server to a project. Returns integer autoincrement ID."""
    with get_connection() as conn:
        try:
            columns = ["project_id", "mcp_server_id"]
            values = [project_id, mcp_server_id]
            if config_override is not None:
                columns.append("config_override")
                values.append(config_override)
            if env_overrides_json is not None:
                columns.append("env_overrides_json")
                values.append(env_overrides_json)
            placeholders = ", ".join("?" for _ in values)
            col_str = ", ".join(columns)
            cursor = conn.execute(
                f"INSERT INTO project_mcp_servers ({col_str}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_project_mcp_servers(project_id: str) -> List[dict]:
    """Get all MCP servers assigned to a project, with server details via JOIN."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT pms.*, ms.name as server_name, ms.description as server_description,
                   ms.server_type, ms.command, ms.args, ms.env_json, ms.url,
                   ms.enabled, ms.display_name, ms.category, ms.headers_json,
                   ms.timeout_ms, ms.is_preset, ms.icon, ms.documentation_url,
                   ms.npm_package,
                   pms.enabled as assignment_enabled, pms.env_overrides_json
            FROM project_mcp_servers pms
            JOIN mcp_servers ms ON pms.mcp_server_id = ms.id
            WHERE pms.project_id = ?
            ORDER BY ms.name ASC
        """,
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_project_mcp_assignment(
    project_id: str,
    mcp_server_id: str,
    enabled: int = None,
    env_overrides_json: str = None,
) -> bool:
    """Update a project-MCP assignment (toggle enable/disable, set env overrides).

    Returns True on success, False if no matching assignment found.
    """
    updates = []
    values = []
    if enabled is not None:
        updates.append("enabled = ?")
        values.append(enabled)
    if env_overrides_json is not None:
        updates.append("env_overrides_json = ?")
        values.append(env_overrides_json)

    if not updates:
        return False

    values.extend([project_id, mcp_server_id])

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE project_mcp_servers SET {', '.join(updates)} "
            "WHERE project_id = ? AND mcp_server_id = ?",
            values,
        )
        conn.commit()
        return cursor.rowcount > 0


def unassign_mcp_from_project(project_id: str, mcp_server_id: str) -> bool:
    """Remove an MCP server assignment from a project. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_mcp_servers WHERE project_id = ? AND mcp_server_id = ?",
            (project_id, mcp_server_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Execution Type Handler CRUD
# =============================================================================


def add_execution_type_handler(
    execution_type: str,
    handler_type: str,
    handler_config: str = None,
    priority: int = 0,
) -> Optional[int]:
    """Add an execution type handler. Returns integer autoincrement ID."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO execution_type_handlers
                (execution_type, handler_type, handler_config, priority)
                VALUES (?, ?, ?, ?)
            """,
                (execution_type, handler_type, handler_config, priority),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_handlers_for_type(execution_type: str) -> List[dict]:
    """Get all handlers for an execution type, ordered by priority DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM execution_type_handlers WHERE execution_type = ? ORDER BY priority DESC",
            (execution_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_all_execution_type_handlers() -> List[dict]:
    """Get all execution type handlers."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM execution_type_handlers ORDER BY execution_type ASC, priority DESC"
        )
        return [dict(row) for row in cursor.fetchall()]


def update_execution_type_handler(handler_id: int, **kwargs) -> bool:
    """Update execution type handler fields. Returns True on success.

    Supported kwargs: execution_type, handler_type, handler_config, priority, enabled.
    """
    allowed = {"execution_type", "handler_type", "handler_config", "priority", "enabled"}
    updates = []
    values = []

    for key, value in kwargs.items():
        if key in allowed and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(handler_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE execution_type_handlers SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_execution_type_handler(handler_id: int) -> bool:
    """Delete an execution type handler. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM execution_type_handlers WHERE id = ?", (handler_id,))
        conn.commit()
        return cursor.rowcount > 0
