"""Plugin, component, marketplace, sync state, and plugin export CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _generate_short_id, _get_unique_plugin_id

logger = logging.getLogger(__name__)


# =============================================================================
# Plugin CRUD operations
# =============================================================================


def add_plugin(
    name: str,
    description: str = None,
    version: str = "1.0.0",
    status: str = "draft",
    author: str = None,
) -> Optional[str]:
    """Add a new plugin. Returns plugin_id on success, None on failure."""
    with get_connection() as conn:
        try:
            plugin_id = _get_unique_plugin_id(conn)
            conn.execute(
                """
                INSERT INTO plugins (id, name, description, version, status, author)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (plugin_id, name, description, version, status, author),
            )
            conn.commit()
            return plugin_id
        except sqlite3.IntegrityError:
            return None


def update_plugin(
    plugin_id: str,
    name: str = None,
    description: str = None,
    version: str = None,
    status: str = None,
    author: str = None,
) -> bool:
    """Update plugin fields. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if version is not None:
        updates.append("version = ?")
        values.append(version)
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if author is not None:
        updates.append("author = ?")
        values.append(author)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(plugin_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE plugins SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_plugin(plugin_id: str) -> bool:
    """Delete a plugin. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM plugins WHERE id = ?", (plugin_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_plugin(plugin_id: str) -> Optional[dict]:
    """Get a single plugin by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM plugins WHERE id = ?", (plugin_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_plugins(limit: Optional[int] = None, offset: int = 0) -> List[dict]:
    """Get all plugins with component counts, with optional pagination."""
    with get_connection() as conn:
        sql = """
            SELECT p.*, COUNT(pc.id) as component_count
            FROM plugins p
            LEFT JOIN plugin_components pc ON p.id = pc.plugin_id
            GROUP BY p.id
            ORDER BY p.name ASC
        """
        params: list = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_plugins() -> int:
    """Count total number of plugins."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM plugins")
        return cursor.fetchone()[0]


def get_plugin_detail(plugin_id: str) -> Optional[dict]:
    """Get plugin with components."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM plugins WHERE id = ?", (plugin_id,))
        row = cursor.fetchone()
        if not row:
            return None
        plugin = dict(row)
        cursor = conn.execute(
            "SELECT * FROM plugin_components WHERE plugin_id = ? ORDER BY type, name ASC",
            (plugin_id,),
        )
        plugin["components"] = [dict(r) for r in cursor.fetchall()]
        return plugin


# =============================================================================
# Plugin component operations
# =============================================================================


def get_plugin_component_by_name(plugin_id: str, name: str, component_type: str) -> Optional[dict]:
    """Get a plugin component by plugin_id, name, and type."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM plugin_components WHERE plugin_id = ? AND name = ? AND type = ?",
            (plugin_id, name, component_type),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def add_plugin_component(
    plugin_id: str, name: str, component_type: str, content: str = None
) -> Optional[int]:
    """Add a component to a plugin. Returns component id on success."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO plugin_components (plugin_id, name, type, content)
                VALUES (?, ?, ?, ?)
            """,
                (plugin_id, name, component_type, content),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_plugin_component(
    component_id: int, name: str = None, component_type: str = None, content: str = None
) -> bool:
    """Update a plugin component. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if component_type is not None:
        updates.append("type = ?")
        values.append(component_type)
    if content is not None:
        updates.append("content = ?")
        values.append(content)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(component_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE plugin_components SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_plugin_component(component_id: int) -> bool:
    """Delete a plugin component. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM plugin_components WHERE id = ?", (component_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_plugin_components(plugin_id: str) -> List[dict]:
    """Get all components of a plugin."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM plugin_components WHERE plugin_id = ? ORDER BY type, name ASC",
            (plugin_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Marketplace functions
# =============================================================================


def add_marketplace(
    name: str,
    url: str,
    marketplace_type: str = "git",
    is_default: bool = False,
) -> Optional[str]:
    """Add a new marketplace."""
    marketplace_id = f"mkt-{_generate_short_id()}"
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO marketplaces (id, name, url, type, is_default)
                VALUES (?, ?, ?, ?, ?)
                """,
                (marketplace_id, name, url, marketplace_type, is_default),
            )
            conn.commit()
            return marketplace_id
        except sqlite3.Error as e:
            logger.error(f"Database error in add_marketplace: {e}")
            return None


def get_marketplace(marketplace_id: str) -> Optional[dict]:
    """Get a marketplace by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM marketplaces WHERE id = ?", (marketplace_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_marketplaces() -> List[dict]:
    """Get all marketplaces."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM marketplaces ORDER BY is_default DESC, name ASC")
        return [dict(row) for row in cursor.fetchall()]


def update_marketplace(
    marketplace_id: str,
    name: Optional[str] = None,
    url: Optional[str] = None,
    marketplace_type: Optional[str] = None,
    is_default: Optional[bool] = None,
) -> bool:
    """Update a marketplace."""
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if url is not None:
        updates.append("url = ?")
        params.append(url)
    if marketplace_type is not None:
        updates.append("type = ?")
        params.append(marketplace_type)
    if is_default is not None:
        updates.append("is_default = ?")
        params.append(is_default)

    if not updates:
        return False

    params.append(marketplace_id)
    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE marketplaces SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_marketplace(marketplace_id: str) -> bool:
    """Delete a marketplace."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM marketplaces WHERE id = ?", (marketplace_id,))
        conn.commit()
        return cursor.rowcount > 0


def add_marketplace_plugin(
    marketplace_id: str,
    remote_name: str,
    plugin_id: Optional[str] = None,
    version: Optional[str] = None,
) -> Optional[str]:
    """Add a plugin installed from a marketplace."""
    mktp_id = f"mktp-{_generate_short_id()}"
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO marketplace_plugins (id, marketplace_id, plugin_id, remote_name, version)
                VALUES (?, ?, ?, ?, ?)
                """,
                (mktp_id, marketplace_id, plugin_id, remote_name, version),
            )
            conn.commit()
            return mktp_id
        except sqlite3.Error as e:
            logger.error(f"Database error in add_marketplace_plugin: {e}")
            return None


def get_marketplace_plugins(marketplace_id: str) -> List[dict]:
    """Get all plugins installed from a marketplace."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM marketplace_plugins WHERE marketplace_id = ? ORDER BY remote_name ASC",
            (marketplace_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_marketplace_plugin(plugin_id: str) -> bool:
    """Delete a marketplace plugin record."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM marketplace_plugins WHERE id = ?", (plugin_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Sync state operations
# =============================================================================


def add_sync_state(
    plugin_id: str,
    entity_type: str,
    entity_id: str,
    file_path: str,
    content_hash: str = None,
    sync_direction: str = None,
) -> Optional[int]:
    """Add a sync state entry. Returns id on success, None on duplicate/error."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO sync_state (plugin_id, entity_type, entity_id, file_path, content_hash, last_synced_at, sync_direction)
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
            """,
                (plugin_id, entity_type, entity_id, file_path, content_hash, sync_direction),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database error in add_sync_state: {e}")
            return None


def get_sync_state(plugin_id: str, entity_type: str, entity_id: str) -> Optional[dict]:
    """Get sync state for a specific entity in a plugin."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM sync_state WHERE plugin_id = ? AND entity_type = ? AND entity_id = ?",
            (plugin_id, entity_type, entity_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_sync_states_for_plugin(plugin_id: str) -> List[dict]:
    """Get all sync state entries for a plugin."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM sync_state WHERE plugin_id = ? ORDER BY entity_type, entity_id",
            (plugin_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_sync_state(
    plugin_id: str,
    entity_type: str,
    entity_id: str,
    content_hash: str = None,
    sync_direction: str = None,
) -> bool:
    """Update sync state for a specific entity. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE sync_state
            SET content_hash = ?, sync_direction = ?, last_synced_at = datetime('now')
            WHERE plugin_id = ? AND entity_type = ? AND entity_id = ?
        """,
            (content_hash, sync_direction, plugin_id, entity_type, entity_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_sync_states_for_plugin(plugin_id: str) -> bool:
    """Delete all sync state entries for a plugin. Returns True if any deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM sync_state WHERE plugin_id = ?", (plugin_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Plugin exports CRUD operations
# =============================================================================


def add_plugin_export(
    plugin_id: str,
    team_id: str = None,
    export_format: str = "claude",
    export_path: str = None,
    marketplace_id: str = None,
    version: str = "1.0.0",
) -> Optional[int]:
    """Add a plugin export record. Returns id on success."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO plugin_exports (plugin_id, team_id, export_format, export_path, marketplace_id, version)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (plugin_id, team_id, export_format, export_path, marketplace_id, version),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database error in add_plugin_export: {e}")
            return None


def get_plugin_export(export_id: int) -> Optional[dict]:
    """Get a plugin export record by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM plugin_exports WHERE id = ?", (export_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_plugin_exports_for_plugin(plugin_id: str) -> List[dict]:
    """Get all export records for a plugin."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM plugin_exports WHERE plugin_id = ? ORDER BY created_at DESC",
            (plugin_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_plugin_export(
    export_id: int,
    status: str = None,
    export_path: str = None,
    last_exported_at: str = None,
) -> bool:
    """Update a plugin export record. Returns True on success."""
    updates = []
    values = []
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if export_path is not None:
        updates.append("export_path = ?")
        values.append(export_path)
    if last_exported_at is not None:
        updates.append("last_exported_at = ?")
        values.append(last_exported_at)
    if not updates:
        return False
    values.append(export_id)
    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE plugin_exports SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_plugin_export(export_id: int) -> bool:
    """Delete a plugin export record. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM plugin_exports WHERE id = ?", (export_id,))
        conn.commit()
        return cursor.rowcount > 0
