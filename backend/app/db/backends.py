"""Backend accounts, fallback chains, and agent session CRUD operations."""

import json
import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


# =============================================================================
# Row-mapping helpers
# =============================================================================


def _row_to_backend(row) -> dict:
    """Convert a database row to a backend dict."""
    backend = dict(row)
    if backend.get("models"):
        try:
            backend["models"] = json.loads(backend["models"])
        except (json.JSONDecodeError, TypeError):
            backend["models"] = []
    return backend


def _row_to_account(row) -> dict:
    """Convert a database row to an account dict."""
    account = dict(row)
    if account.get("usage_data"):
        try:
            account["usage_data"] = json.loads(account["usage_data"])
        except (json.JSONDecodeError, TypeError):
            account["usage_data"] = {}
    return account


# =============================================================================
# Fallback Chain CRUD operations
# =============================================================================


def get_fallback_chain(entity_type: str, entity_id: str) -> List[dict]:
    """Get the fallback chain for an entity, ordered by chain_order."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM fallback_chains WHERE entity_type = ? AND entity_id = ? ORDER BY chain_order ASC",
            (entity_type, entity_id),
        )
        return [dict(row) for row in cursor.fetchall()]


def set_fallback_chain(entity_type: str, entity_id: str, entries: list) -> bool:
    """Set (replace) the fallback chain for an entity. Transactional delete + insert.

    entries: list of dicts with keys 'backend_type' and optional 'account_id'.
    Returns True on success.
    """
    with get_connection() as conn:
        try:
            conn.execute(
                "DELETE FROM fallback_chains WHERE entity_type = ? AND entity_id = ?",
                (entity_type, entity_id),
            )
            for i, entry in enumerate(entries):
                conn.execute(
                    """
                    INSERT INTO fallback_chains (entity_type, entity_id, chain_order, backend_type, account_id)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        entity_type,
                        entity_id,
                        i,
                        entry["backend_type"],
                        entry.get("account_id"),
                    ),
                )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def delete_fallback_chain(entity_type: str, entity_id: str) -> bool:
    """Delete all fallback chain entries for an entity. Returns True if any deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM fallback_chains WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Backend Account CRUD operations
# =============================================================================


def get_accounts_for_backend_type(backend_type: str) -> List[dict]:
    """Get all accounts for a given backend type (joins ai_backends on type)."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT ba.* FROM backend_accounts ba
            JOIN ai_backends ab ON ba.backend_id = ab.id
            WHERE ab.type = ?
            ORDER BY ba.is_default DESC, ba.last_used_at ASC
        """,
            (backend_type,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_account_rate_limit(account_id: int, limited_until: str, reason: str) -> bool:
    """Update rate limit state for an account. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE backend_accounts SET rate_limited_until = ?, rate_limit_reason = ? WHERE id = ?",
            (limited_until, reason, account_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def clear_account_rate_limit(account_id: int) -> bool:
    """Clear rate limit for an account. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE backend_accounts SET rate_limited_until = NULL, rate_limit_reason = NULL WHERE id = ?",
            (account_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_account_rate_limit_state(account_id: int) -> Optional[dict]:
    """Get rate limit state for an account."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, rate_limited_until, rate_limit_reason FROM backend_accounts WHERE id = ?",
            (account_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def increment_account_executions(account_id: int) -> bool:
    """Increment total_executions and set last_used_at for an account."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE backend_accounts SET total_executions = COALESCE(total_executions, 0) + 1, last_used_at = datetime('now') WHERE id = ?",
            (account_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_all_accounts_with_health(backend_type: str = None) -> List[dict]:
    """Get all accounts with rate limit health info, optionally filtered by backend type."""
    with get_connection() as conn:
        if backend_type:
            cursor = conn.execute(
                """
                SELECT ba.*, ab.type as backend_type, ab.name as backend_name
                FROM backend_accounts ba
                JOIN ai_backends ab ON ba.backend_id = ab.id
                WHERE ab.type = ?
                ORDER BY ab.type, ba.is_default DESC, ba.account_name
            """,
                (backend_type,),
            )
        else:
            cursor = conn.execute("""
                SELECT ba.*, ab.type as backend_type, ab.name as backend_name
                FROM backend_accounts ba
                JOIN ai_backends ab ON ba.backend_id = ab.id
                ORDER BY ab.type, ba.is_default DESC, ba.account_name
            """)
        return [dict(row) for row in cursor.fetchall()]


def update_backend_last_used(backend_type: str):
    """Update last_used_at timestamp for a backend by type."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE ai_backends SET last_used_at = datetime('now') WHERE type = ?",
            (backend_type,),
        )
        conn.commit()


def update_backend_models(backend_id: str, models: list[str]):
    """Update the models list for a backend."""
    import json as _json

    with get_connection() as conn:
        conn.execute(
            "UPDATE ai_backends SET models = ? WHERE id = ?",
            (_json.dumps(models), backend_id),
        )
        conn.commit()


def auto_enable_monitoring_for_account(account_id: int):
    """If global monitoring is enabled, auto-add a new account to monitoring config."""
    # Lazy import to avoid cross-domain circular dependency
    from .monitoring import get_monitoring_config, save_monitoring_config

    config = get_monitoring_config()
    if not config.get("enabled"):
        return
    accounts = config.get("accounts", {})
    acct_key = str(account_id)
    if acct_key not in accounts:
        accounts[acct_key] = {"enabled": True}
        config["accounts"] = accounts
        save_monitoring_config(config)


def get_account_with_backend(account_id: int) -> Optional[dict]:
    """Get a backend account joined with its backend type info."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT ba.*, ab.type as backend_type, ab.name as backend_name
            FROM backend_accounts ba
            JOIN ai_backends ab ON ba.backend_id = ab.id
            WHERE ba.id = ?
            """,
            (account_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# =============================================================================
# Backend CRUD operations (used by BackendService)
# =============================================================================


def get_all_backends() -> list[dict]:
    """Get all backends with account counts, emails, and last used timestamps.

    last_used_at comes directly from the ai_backends column, which is kept
    up-to-date by update_backend_last_used() after each chat stream.
    """
    with get_connection() as conn:
        cursor = conn.execute("""SELECT b.*,
                      (SELECT COUNT(*) FROM backend_accounts WHERE backend_id = b.id) as account_count,
                      (SELECT GROUP_CONCAT(ba.email, ', ')
                       FROM backend_accounts ba
                       WHERE ba.backend_id = b.id AND ba.email IS NOT NULL AND ba.email != ''
                      ) as account_emails
               FROM ai_backends b ORDER BY name""")
        return [_row_to_backend(row) for row in cursor.fetchall()]


def get_backend_by_id(backend_id: str) -> Optional[dict]:
    """Get a single backend by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM ai_backends WHERE id = ?", (backend_id,))
        row = cursor.fetchone()
        return _row_to_backend(row) if row else None


def get_backend_accounts(backend_id: str) -> list[dict]:
    """Get all accounts for a backend, ordered by default status then name."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM backend_accounts WHERE backend_id = ? ORDER BY is_default DESC, account_name",
            (backend_id,),
        )
        return [_row_to_account(row) for row in cursor.fetchall()]


def get_backend_type(backend_id: str) -> Optional[str]:
    """Get the type of a backend by ID. Returns None if not found."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT type FROM ai_backends WHERE id = ?", (backend_id,))
        row = cursor.fetchone()
        return row["type"] if row else None


def create_backend_account(
    backend_id: str,
    account_name: str,
    email: Optional[str],
    config_path: Optional[str],
    api_key_env: Optional[str],
    is_default: int,
    plan: Optional[str],
    usage_data: Optional[dict],
) -> Optional[int]:
    """Create a new backend account. Handles default-unsetting logic. Returns lastrowid."""
    usage_data_json = json.dumps(usage_data) if usage_data else None
    with get_connection() as conn:
        # If marked as default, unset other defaults
        if is_default:
            conn.execute(
                "UPDATE backend_accounts SET is_default = 0 WHERE backend_id = ?",
                (backend_id,),
            )

        cursor = conn.execute(
            """
            INSERT INTO backend_accounts (backend_id, account_name, email, config_path, api_key_env, is_default, plan, usage_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                backend_id,
                account_name,
                email,
                config_path,
                api_key_env,
                is_default or 0,
                plan,
                usage_data_json,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def update_backend_account(
    account_id: int,
    backend_id: str,
    account_name: Optional[str] = None,
    email: Optional[str] = None,
    config_path: Optional[str] = None,
    api_key_env: Optional[str] = None,
    is_default: Optional[int] = None,
    plan: Optional[str] = None,
    usage_data: Optional[dict] = None,
) -> bool:
    """Update a backend account. Returns True if updated, False if not found."""
    with get_connection() as conn:
        # Check account exists
        cursor = conn.execute(
            "SELECT id FROM backend_accounts WHERE id = ? AND backend_id = ?",
            (account_id, backend_id),
        )
        if not cursor.fetchone():
            return False

        updates = []
        values = []

        if account_name is not None:
            updates.append("account_name = ?")
            values.append(account_name)
        if email is not None:
            updates.append("email = ?")
            values.append(email)
        if config_path is not None:
            updates.append("config_path = ?")
            values.append(config_path)
        if api_key_env is not None:
            updates.append("api_key_env = ?")
            values.append(api_key_env)
        if is_default is not None:
            if is_default:
                # Unset other defaults first
                conn.execute(
                    "UPDATE backend_accounts SET is_default = 0 WHERE backend_id = ?",
                    (backend_id,),
                )
            updates.append("is_default = ?")
            values.append(is_default)
        if plan is not None:
            updates.append("plan = ?")
            values.append(plan)
        if usage_data is not None:
            updates.append("usage_data = ?")
            values.append(json.dumps(usage_data))

        if not updates:
            return True  # No fields to update, but account exists

        values.append(account_id)
        conn.execute(f"UPDATE backend_accounts SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return True


def delete_backend_account(account_id: int, backend_id: str) -> bool:
    """Delete a backend account. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM backend_accounts WHERE id = ? AND backend_id = ?",
            (account_id, backend_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def check_and_update_backend_installed(
    backend_id: str, installed: bool, version: Optional[str]
) -> bool:
    """Update is_installed and version for a backend."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE ai_backends SET is_installed = ?, version = ? WHERE id = ?",
            (1 if installed else 0, version, backend_id),
        )
        conn.commit()
        return True


def get_backend_accounts_for_auth(backend_id: str) -> list[dict]:
    """Get all accounts for a backend as raw dicts (for auth status checks)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM backend_accounts WHERE backend_id = ?",
            (backend_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def verify_account_exists(account_id: int, backend_id: str) -> bool:
    """Check if a backend account exists."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id FROM backend_accounts WHERE id = ? AND backend_id = ?",
            (account_id, backend_id),
        )
        return cursor.fetchone() is not None


# =============================================================================
# Agent Session CRUD (Scheduler)
# =============================================================================


def get_agent_session(account_id: int) -> dict | None:
    """Get the scheduler session for an account. Returns dict or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, account_id, state, stop_reason, stop_window_type, "
            "stop_eta_minutes, resume_estimate, consecutive_safe_polls, updated_at "
            "FROM agent_sessions WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "account_id": row["account_id"],
            "state": row["state"],
            "stop_reason": row["stop_reason"],
            "stop_window_type": row["stop_window_type"],
            "stop_eta_minutes": row["stop_eta_minutes"],
            "resume_estimate": row["resume_estimate"],
            "consecutive_safe_polls": row["consecutive_safe_polls"],
            "updated_at": row["updated_at"],
        }


def get_all_agent_sessions() -> list:
    """Get all scheduler sessions. Returns list of dicts."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, account_id, state, stop_reason, stop_window_type, "
            "stop_eta_minutes, resume_estimate, consecutive_safe_polls, updated_at "
            "FROM agent_sessions ORDER BY account_id"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "account_id": row["account_id"],
                "state": row["state"],
                "stop_reason": row["stop_reason"],
                "stop_window_type": row["stop_window_type"],
                "stop_eta_minutes": row["stop_eta_minutes"],
                "resume_estimate": row["resume_estimate"],
                "consecutive_safe_polls": row["consecutive_safe_polls"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]


def upsert_agent_session(
    account_id: int,
    state: str,
    stop_reason: str | None = None,
    stop_window_type: str | None = None,
    stop_eta_minutes: float | None = None,
    resume_estimate: str | None = None,
    consecutive_safe_polls: int = 0,
) -> bool:
    """Insert or replace a scheduler session for an account."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_sessions
                (account_id, state, stop_reason, stop_window_type,
                 stop_eta_minutes, resume_estimate, consecutive_safe_polls, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(account_id) DO UPDATE SET
                state = excluded.state,
                stop_reason = excluded.stop_reason,
                stop_window_type = excluded.stop_window_type,
                stop_eta_minutes = excluded.stop_eta_minutes,
                resume_estimate = excluded.resume_estimate,
                consecutive_safe_polls = excluded.consecutive_safe_polls,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                account_id,
                state,
                stop_reason,
                stop_window_type,
                stop_eta_minutes,
                resume_estimate,
                consecutive_safe_polls,
            ),
        )
        conn.commit()
        return True


def delete_agent_session(account_id: int) -> bool:
    """Delete the scheduler session for an account. Returns True if a row was deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM agent_sessions WHERE account_id = ?",
            (account_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# CLIProxyAPI proxy configuration helpers
# =============================================================================


def get_proxy_enabled_accounts() -> List[dict]:
    """Get all backend accounts with use_proxy = 1."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT ba.*, ab.type as backend_type
            FROM backend_accounts ba
            JOIN ai_backends ab ON ba.backend_id = ab.id
            WHERE ba.use_proxy = 1
            ORDER BY ba.id
            """,
        )
        return [dict(row) for row in cursor.fetchall()]


def get_claude_code_accounts() -> List[dict]:
    """Get all Claude Code backend accounts (type='claude')."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT ba.*, ab.type as backend_type
            FROM backend_accounts ba
            JOIN ai_backends ab ON ba.backend_id = ab.id
            WHERE ab.type = 'claude'
            ORDER BY ba.id
            """,
        )
        return [dict(row) for row in cursor.fetchall()]


def update_account_proxy_config(account_id: int, proxy_port: Optional[int], use_proxy: int) -> bool:
    """Update proxy_port and use_proxy for a backend account. Returns True if updated."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE backend_accounts SET proxy_port = ?, use_proxy = ? WHERE id = ?",
            (proxy_port, use_proxy, account_id),
        )
        conn.commit()
        return cursor.rowcount > 0
