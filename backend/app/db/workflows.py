"""Workflow CRUD operations, version tracking, execution tracking, and DAG validation."""

import graphlib
import json
import logging
import sqlite3
from typing import List, Optional, Tuple

from .connection import get_connection
from .ids import _get_unique_workflow_execution_id, _get_unique_workflow_id

logger = logging.getLogger(__name__)


# =============================================================================
# DAG Validation
# =============================================================================


def validate_workflow_graph(graph_json_str: str) -> Tuple[bool, str]:
    """Validate that a workflow graph is a valid DAG.

    Uses graphlib.TopologicalSorter (stdlib Python 3.9+) for cycle detection.

    Args:
        graph_json_str: JSON string containing {"nodes": [...], "edges": [...]}.

    Returns:
        Tuple of (is_valid, error_message). error_message is empty when valid.
    """
    try:
        graph = json.loads(graph_json_str)
    except (json.JSONDecodeError, TypeError) as e:
        return False, f"Invalid JSON: {e}"

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        return False, "Graph must have at least one node"

    # Build node ID set
    node_ids = set()
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            return False, "Each node must have an 'id' field"
        node_ids.add(node_id)

    # Validate edges reference existing nodes
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_ids:
            return False, f"Edge references unknown source node: {source}"
        if target not in node_ids:
            return False, f"Edge references unknown target node: {target}"

    # Build dependency dict for TopologicalSorter
    # Each node depends on its predecessors (source -> target means target depends on source)
    deps = {node_id: set() for node_id in node_ids}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        deps[target].add(source)

    try:
        ts = graphlib.TopologicalSorter(deps)
        ts.prepare()
    except graphlib.CycleError as e:
        return False, f"Graph contains a cycle: {e}"

    return True, ""


# =============================================================================
# Workflow CRUD
# =============================================================================


def add_workflow(
    name: str,
    description: str = None,
    trigger_type: str = "manual",
    trigger_config: str = None,
) -> Optional[str]:
    """Add a new workflow. Returns workflow_id on success, None on failure."""
    with get_connection() as conn:
        try:
            workflow_id = _get_unique_workflow_id(conn)
            conn.execute(
                """
                INSERT INTO workflows (id, name, description, trigger_type, trigger_config)
                VALUES (?, ?, ?, ?, ?)
            """,
                (workflow_id, name, description, trigger_type, trigger_config),
            )
            conn.commit()
            return workflow_id
        except sqlite3.IntegrityError:
            return None


def get_workflow(workflow_id: str) -> Optional[dict]:
    """Get a single workflow by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_workflows() -> List[dict]:
    """Get all workflows with latest version number."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT w.*, COALESCE(MAX(wv.version), 0) as latest_version
            FROM workflows w
            LEFT JOIN workflow_versions wv ON w.id = wv.workflow_id
            GROUP BY w.id
            ORDER BY w.name ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def update_workflow(
    workflow_id: str,
    name: str = None,
    description: str = None,
    trigger_type: str = None,
    trigger_config: str = None,
    enabled: int = None,
) -> bool:
    """Update workflow fields. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if trigger_type is not None:
        updates.append("trigger_type = ?")
        values.append(trigger_type)
    if trigger_config is not None:
        updates.append("trigger_config = ?")
        values.append(trigger_config)
    if enabled is not None:
        updates.append("enabled = ?")
        values.append(enabled)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(workflow_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE workflows SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_workflow(workflow_id: str) -> bool:
    """Delete a workflow. CASCADE handles versions and executions. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Version Tracking
# =============================================================================


def add_workflow_version(workflow_id: str, graph_json: str, is_draft: bool = False) -> Optional[int]:
    """Add a new workflow version with auto-incrementing version number.

    Validates graph_json is valid JSON and a valid DAG before inserting.

    Args:
        workflow_id: The workflow to add a version for.
        graph_json: JSON string of the workflow graph.
        is_draft: If True, save as a draft that won't be picked up for execution.

    Returns:
        The new version number on success, None on failure.
    """
    # Validate JSON
    try:
        json.loads(graph_json)
    except (json.JSONDecodeError, TypeError):
        return None

    # Validate DAG
    is_valid, error = validate_workflow_graph(graph_json)
    if not is_valid:
        return None

    with get_connection() as conn:
        try:
            # Auto-increment version number
            cursor = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM workflow_versions WHERE workflow_id = ?",
                (workflow_id,),
            )
            version = cursor.fetchone()[0]

            conn.execute(
                """
                INSERT INTO workflow_versions (workflow_id, version, graph_json, is_draft)
                VALUES (?, ?, ?, ?)
            """,
                (workflow_id, version, graph_json, 1 if is_draft else 0),
            )
            conn.commit()
            return version
        except sqlite3.IntegrityError:
            return None


def add_workflow_version_raw(
    workflow_id: str, graph_json: str, is_draft: bool = False
) -> Tuple[Optional[int], str]:
    """Add a new workflow version, returning (version, error) for detailed error reporting.

    This variant returns the validation error message so routes can forward it to clients.

    Args:
        workflow_id: The workflow to add a version for.
        graph_json: JSON string of the workflow graph.
        is_draft: If True, save as a draft that won't be picked up for execution.

    Returns:
        Tuple of (version_number, error_message). version_number is None on failure.
    """
    # Validate JSON
    try:
        json.loads(graph_json)
    except (json.JSONDecodeError, TypeError) as e:
        return None, f"Invalid JSON: {e}"

    # Validate DAG
    is_valid, error = validate_workflow_graph(graph_json)
    if not is_valid:
        return None, error

    with get_connection() as conn:
        try:
            # Auto-increment version number
            cursor = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM workflow_versions WHERE workflow_id = ?",
                (workflow_id,),
            )
            version = cursor.fetchone()[0]

            conn.execute(
                """
                INSERT INTO workflow_versions (workflow_id, version, graph_json, is_draft)
                VALUES (?, ?, ?, ?)
            """,
                (workflow_id, version, graph_json, 1 if is_draft else 0),
            )
            conn.commit()
            return version, ""
        except sqlite3.IntegrityError as e:
            return None, f"Database error: {e}"


def publish_workflow_version(workflow_id: str, version: int) -> bool:
    """Promote a draft version to published (is_draft=0). Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE workflow_versions SET is_draft = 0 WHERE workflow_id = ? AND version = ?",
            (workflow_id, version),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_workflow_versions(workflow_id: str) -> List[dict]:
    """Get all versions for a workflow, ordered by version DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflow_versions WHERE workflow_id = ? ORDER BY version DESC",
            (workflow_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_latest_workflow_version(workflow_id: str) -> Optional[dict]:
    """Get the latest published (non-draft) version for a workflow."""
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT * FROM workflow_versions
               WHERE workflow_id = ? AND is_draft = 0
               ORDER BY version DESC LIMIT 1""",
            (workflow_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# =============================================================================
# Execution Tracking
# =============================================================================


def add_workflow_execution(
    workflow_id: str,
    version: int,
    input_json: str = None,
    status: str = "running",
) -> Optional[str]:
    """Add a new workflow execution record. Returns execution_id on success."""
    with get_connection() as conn:
        try:
            execution_id = _get_unique_workflow_execution_id(conn)
            conn.execute(
                """
                INSERT INTO workflow_executions (id, workflow_id, version, status, input_json)
                VALUES (?, ?, ?, ?, ?)
            """,
                (execution_id, workflow_id, version, status, input_json),
            )
            conn.commit()
            return execution_id
        except sqlite3.IntegrityError:
            return None


def update_workflow_execution(
    execution_id: str,
    status: str = None,
    output_json: str = None,
    error: str = None,
    ended_at: str = None,
) -> bool:
    """Update workflow execution fields. Returns True on success."""
    updates = []
    values = []

    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if output_json is not None:
        updates.append("output_json = ?")
        values.append(output_json)
    if error is not None:
        updates.append("error = ?")
        values.append(error)
    if ended_at is not None:
        updates.append("ended_at = ?")
        values.append(ended_at)

    if not updates:
        return False

    values.append(execution_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE workflow_executions SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def get_workflow_execution(execution_id: str) -> Optional[dict]:
    """Get a single workflow execution by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM workflow_executions WHERE id = ?", (execution_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_workflow_executions(workflow_id: str) -> List[dict]:
    """Get all executions for a workflow, ordered by started_at DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflow_executions WHERE workflow_id = ? ORDER BY started_at DESC",
            (workflow_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_running_workflow_executions() -> List[dict]:
    """Get all workflow executions currently marked as 'running' in the DB."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflow_executions WHERE status = 'running'",
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Node Execution Tracking
# =============================================================================


def add_workflow_node_execution(
    execution_id: str,
    node_id: str,
    node_type: str,
    input_json: str = None,
) -> Optional[int]:
    """Add a node execution record. Returns the row id on success."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO workflow_node_executions (execution_id, node_id, node_type, input_json)
                VALUES (?, ?, ?, ?)
            """,
                (execution_id, node_id, node_type, input_json),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_workflow_node_execution(
    node_exec_id: int,
    status: str = None,
    output_json: str = None,
    error: str = None,
    started_at: str = None,
    ended_at: str = None,
) -> bool:
    """Update workflow node execution fields. Returns True on success."""
    updates = []
    values = []

    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if output_json is not None:
        updates.append("output_json = ?")
        values.append(output_json)
    if error is not None:
        updates.append("error = ?")
        values.append(error)
    if started_at is not None:
        updates.append("started_at = ?")
        values.append(started_at)
    if ended_at is not None:
        updates.append("ended_at = ?")
        values.append(ended_at)

    if not updates:
        return False

    values.append(node_exec_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE workflow_node_executions SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        conn.commit()
        return cursor.rowcount > 0


def get_workflow_node_executions(execution_id: str) -> List[dict]:
    """Get all node executions for a workflow execution, ordered by started_at ASC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflow_node_executions WHERE execution_id = ? ORDER BY started_at ASC",
            (execution_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
