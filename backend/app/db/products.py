"""Product CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_product_id

logger = logging.getLogger(__name__)


# =============================================================================
# Product CRUD
# =============================================================================


def _resolve_user_id(conn, user_id: Optional[str]) -> Optional[str]:
    """Default to the legacy user when caller didn't pass one."""
    if user_id:
        return user_id
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("legacy@local",)
    ).fetchone()
    return row[0] if row else None


def create_product(
    name: str,
    description: str = None,
    status: str = "active",
    owner_team_id: str = None,
    owner_agent_id: str = None,
    user_id: Optional[str] = None,
) -> Optional[str]:
    """Add a new product. Returns product_id on success, None on failure.

    ``user_id`` is the owning user (track B, wave 39 multi-tenancy
    starter). When omitted, falls back to the legacy@local user so
    existing single-user call sites keep working.
    """
    with get_connection() as conn:
        try:
            product_id = _get_unique_product_id(conn)
            owner_user_id = _resolve_user_id(conn, user_id)
            conn.execute(
                """
                INSERT INTO products (id, name, description, status, owner_team_id, owner_agent_id, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    product_id,
                    name,
                    description,
                    status,
                    owner_team_id,
                    owner_agent_id,
                    owner_user_id,
                ),
            )
            conn.commit()
            return product_id
        except sqlite3.IntegrityError:
            return None


def update_product(
    product_id: str,
    name: str = None,
    description: str = None,
    status: str = None,
    owner_team_id: str = None,
    owner_agent_id: str = None,
) -> bool:
    """Update product fields. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if owner_team_id is not None:
        updates.append("owner_team_id = ?")
        values.append(owner_team_id if owner_team_id else None)
    if owner_agent_id is not None:
        updates.append("owner_agent_id = ?")
        values.append(owner_agent_id if owner_agent_id else None)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(product_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE products SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_product(product_id: str) -> bool:
    """Delete a product. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_product(product_id: str) -> Optional[dict]:
    """Get a single product by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_products(limit: Optional[int] = None, offset: int = 0) -> List[dict]:
    """Get all products with project counts and owner agent name.

    Unscoped; useful for admin views. Per-user scoping uses
    :func:`get_products_for_user`.
    """
    with get_connection() as conn:
        sql = """
            SELECT p.*, t.name as owner_team_name, sa.name as owner_agent_name,
                   COUNT(pr.id) as project_count
            FROM products p
            LEFT JOIN teams t ON p.owner_team_id = t.id
            LEFT JOIN super_agents sa ON p.owner_agent_id = sa.id
            LEFT JOIN projects pr ON p.id = pr.product_id
            GROUP BY p.id
            ORDER BY p.name ASC
        """
        params: list = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def get_products_for_user(
    user_id: str,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[dict]:
    """Per-user scoped product listing (wave 39 multi-tenancy starter).

    Returns only the products owned by *user_id*. Pattern repeats for
    every other owned-entity table — when migrating those, add a
    sibling ``get_<entity>_for_user`` alongside the unscoped reader.
    """
    with get_connection() as conn:
        sql = """
            SELECT p.*, t.name as owner_team_name, sa.name as owner_agent_name,
                   COUNT(pr.id) as project_count
            FROM products p
            LEFT JOIN teams t ON p.owner_team_id = t.id
            LEFT JOIN super_agents sa ON p.owner_agent_id = sa.id
            LEFT JOIN projects pr ON p.id = pr.product_id
            WHERE p.user_id = ?
            GROUP BY p.id
            ORDER BY p.name ASC
        """
        params: list = [user_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_products() -> int:
    """Count total number of products."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM products")
        return cursor.fetchone()[0]


def get_product_detail(product_id: str) -> Optional[dict]:
    """Get product with projects and owner agent name."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT p.*, t.name as owner_team_name, sa.name as owner_agent_name
            FROM products p
            LEFT JOIN teams t ON p.owner_team_id = t.id
            LEFT JOIN super_agents sa ON p.owner_agent_id = sa.id
            WHERE p.id = ?
        """,
            (product_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        product = dict(row)
        cursor = conn.execute(
            "SELECT * FROM projects WHERE product_id = ? ORDER BY name ASC", (product_id,)
        )
        product["projects"] = [dict(r) for r in cursor.fetchall()]
        return product
