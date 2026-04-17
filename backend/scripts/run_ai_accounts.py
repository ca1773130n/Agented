"""Run the ai-accounts Litestar app alongside Agented's Flask backend.

Listens on 127.0.0.1:20001. The Vite dev server proxies /api/v1/* to this
process; everything else (bots, workflows, teams, etc.) stays on Flask at
port 20000.

This is a transitional arrangement. As more features migrate to
ai-accounts, Flask's responsibilities shrink; post-migration we can either
collapse to one ASGI process or keep the split.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ai_accounts_core.adapters.auth_apikey import ApiKeyAuth
from ai_accounts_core.adapters.auth_noauth import NoAuth
from ai_accounts_core.adapters.storage_sqlite import SqliteStorage
from ai_accounts_core.adapters.vault_envkey import EnvKeyVault
from ai_accounts_core.backends import (
    ClaudeBackend,
    CodexBackend,
    GeminiBackend,
    OpenCodeBackend,
)
from ai_accounts_litestar.app import create_app
from ai_accounts_litestar.config import AiAccountsConfig

logger = logging.getLogger("run_ai_accounts")


def _migrate_legacy_backends(legacy_db: str, target_db: str) -> None:
    """Best-effort one-shot migration of `backend_accounts` from the old
    `agented.db` schema into the new `ai_accounts.db` `backends` table.

    The two schemas diverge significantly:
      - Agented stored grouped rows: `ai_backends` (per kind) + N `backend_accounts`.
      - ai-accounts stores one flat `backends` row per account with credentials
        encrypted in `backend_credentials`.

    We CANNOT migrate credentials (different encryption key + structure), so
    we only seed placeholder `backends` rows preserving `kind`, `display_name`
    and a small subset of config fields. Users still need to re-authenticate
    after upgrade, but their account rows (and the UI selections that reference
    them by kind) no longer vanish silently.

    Runs only if the target `backends` table is empty AND the legacy DB has
    at least one `backend_accounts` row.
    """
    if not os.path.exists(legacy_db):
        return

    # Ensure schema is initialised on the target DB before INSERTing.
    try:
        target = sqlite3.connect(target_db)
    except sqlite3.Error as exc:
        logger.warning("migration: cannot open target %s: %s", target_db, exc)
        return

    try:
        row = target.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='backends'"
        ).fetchone()
        if not row:
            # Target schema not initialised yet; ai-accounts will create it
            # on first use and the migration will no-op on a later start.
            return
        existing = target.execute("SELECT COUNT(*) FROM backends").fetchone()[0]
        if existing:
            return  # already migrated or freshly populated

        legacy = sqlite3.connect(legacy_db)
        legacy.row_factory = sqlite3.Row
        try:
            tables = {r[0] for r in legacy.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            if "backend_accounts" not in tables or "ai_backends" not in tables:
                return
            rows = legacy.execute(
                """
                SELECT ba.id as account_id, ba.account_name, ba.email,
                       ba.config_path, ba.api_key_env, ba.is_default,
                       ba.plan, ab.type as kind
                FROM backend_accounts ba
                JOIN ai_backends ab ON ba.backend_id = ab.id
                """
            ).fetchall()
        finally:
            legacy.close()

        if not rows:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        migrated = 0
        for r in rows:
            kind = r["kind"]
            if not kind:
                continue
            config = {
                "email": r["email"],
                "config_path": r["config_path"],
                "api_key_env": r["api_key_env"],
                "is_default": bool(r["is_default"]),
                "plan": r["plan"],
                "_migrated_from_agented_db": True,
                "_legacy_account_id": r["account_id"],
            }
            target.execute(
                "INSERT INTO backends (id, kind, display_name, config, status, "
                "created_at, updated_at, last_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"bkd-{uuid.uuid4().hex[:12]}",
                    kind,
                    r["account_name"] or r["email"] or kind,
                    json.dumps({k: v for k, v in config.items() if v is not None}),
                    "needs_reauth",
                    now_iso,
                    now_iso,
                    "Migrated from legacy agented.db — please re-authenticate.",
                ),
            )
            migrated += 1
        target.commit()
        if migrated:
            logger.warning(
                "migrated %d legacy backend account(s) from %s to %s as "
                "placeholders (re-authentication required)",
                migrated, legacy_db, target_db,
            )
    except sqlite3.Error as exc:
        logger.warning("migration: skipped due to sqlite error: %s", exc)
    finally:
        target.close()

# Use ApiKeyAuth if AI_ACCOUNTS_API_KEY is set; fall back to NoAuth in dev
_api_key = os.environ.get("AI_ACCOUNTS_API_KEY")
_legacy_db_path = os.path.join(os.path.dirname(__file__), "..", "agented.db")
if not _api_key:
    # In dev, try to read the same key Flask uses from agented.db settings
    try:
        if os.path.exists(_legacy_db_path):
            conn = sqlite3.connect(_legacy_db_path)
            row = conn.execute("SELECT value FROM settings WHERE key = 'api_key'").fetchone()
            conn.close()
            if row:
                _api_key = row[0]
    except Exception:
        pass

# Best-effort migration from the pre-split schema. Safe to call on every
# boot: no-ops once the target table has any rows.
try:
    _migrate_legacy_backends(_legacy_db_path, "./ai_accounts.db")
except Exception as exc:  # pragma: no cover — migration must never crash boot
    logger.warning("legacy backend migration failed: %s", exc)

auth = ApiKeyAuth(token=_api_key) if _api_key else NoAuth()

app = create_app(
    AiAccountsConfig(
        env="development",
        storage=SqliteStorage("./ai_accounts.db"),
        vault=EnvKeyVault.from_env(env="development"),
        auth=auth,
        backends=(
            ClaudeBackend(),
            OpenCodeBackend(),
            GeminiBackend(),
            CodexBackend(),
        ),
        backend_dirs_path=Path("./backend_dirs"),
    )
)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=20001)


if __name__ == "__main__":
    main()
