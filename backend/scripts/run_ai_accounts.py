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

# Pick an auth strategy.
#
# Priority:
#   1. ``AI_ACCOUNTS_API_KEY`` env — explicit static token, always authed.
#   2. Static snapshot from agented.db's ``user_roles`` table (legacy:
#      previous fallback queried ``settings.api_key`` which never existed,
#      so the sidecar silently ran with NoAuth even when Flask was
#      properly keyed — H3 in code review).
#   3. ``LazyFlaskKeyAuth`` — re-reads ``user_roles`` on each request.
#      This makes the sidecar bootable BEFORE Flask has been keyed: it
#      refuses every request until the welcome page inserts a row, and
#      auto-picks up the new key on the very next request without needing
#      a restart.  Without this, ``just deploy`` on a fresh DB would race
#      and the user would see "no API key available" exits.
#   4. ``NoAuth`` only when the operator explicitly opts in via
#      ``AI_ACCOUNTS_ALLOW_NOAUTH=1`` (localhost-only dev mode).
_legacy_db_path = os.path.join(os.path.dirname(__file__), "..", "agented.db")
_env_api_key = os.environ.get("AI_ACCOUNTS_API_KEY")

# Best-effort migration from the pre-split schema. Safe to call on every
# boot: no-ops once the target table has any rows.
try:
    _migrate_legacy_backends(_legacy_db_path, "./ai_accounts.db")
except Exception as exc:  # pragma: no cover — migration must never crash boot
    logger.warning("legacy backend migration failed: %s", exc)


class LazyFlaskKeyAuth:
    """Auth strategy that mirrors Flask's ``user_roles`` admin keys on
    every request.  Lets the sidecar boot before Flask has been keyed
    (returns 401 until a row appears) and auto-picks up new keys without
    a restart.  Bearer-token only, like :class:`ApiKeyAuth`.
    """

    _PREFIX = "bearer "

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        from ai_accounts_core.domain.principal import Principal

        self._principal = Principal(
            id="api_key", display_name="API Key", scopes=frozenset({"*"})
        )

    def _allowed_keys(self) -> set[str]:
        if not os.path.exists(self._db_path):
            return set()
        try:
            conn = sqlite3.connect(self._db_path)
        except sqlite3.Error:
            return set()
        try:
            try:
                rows = conn.execute(
                    "SELECT api_key FROM user_roles WHERE api_key IS NOT NULL"
                ).fetchall()
            except sqlite3.Error:
                return set()
        finally:
            conn.close()
        return {r[0] for r in rows if r and r[0]}

    async def authenticate(self, request):
        import hmac

        header = request.headers.get("authorization") or request.headers.get(
            "Authorization"
        )
        if not header or not header.lower().startswith(self._PREFIX):
            return None
        presented = header[len(self._PREFIX) :]
        for stored in self._allowed_keys():
            if hmac.compare_digest(presented, stored):
                return self._principal
        return None


if _env_api_key:
    auth = ApiKeyAuth(token=_env_api_key)
elif os.environ.get("AI_ACCOUNTS_ALLOW_NOAUTH") == "1":
    logger.warning(
        "ai-accounts: AI_ACCOUNTS_ALLOW_NOAUTH=1 — running with NoAuth. "
        "ALL requests authenticated as 'local'. Never expose port 20001 "
        "or its Vite /api/v1 proxy outside localhost in this mode."
    )
    auth = NoAuth()
else:
    auth = LazyFlaskKeyAuth(_legacy_db_path)
    logger.info(
        "ai-accounts: using LazyFlaskKeyAuth — every request validates "
        "against agented.db's user_roles. Sidecar will refuse traffic "
        "until the welcome page generates an admin key (or until "
        "AI_ACCOUNTS_API_KEY is set in the environment)."
    )

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
