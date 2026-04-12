"""Run the ai-accounts Litestar app alongside Agented's Flask backend.

Listens on 127.0.0.1:20001. The Vite dev server proxies /api/v1/* to this
process; everything else (bots, workflows, teams, etc.) stays on Flask at
port 20000.

This is a transitional arrangement. As more features migrate to
ai-accounts, Flask's responsibilities shrink; post-migration we can either
collapse to one ASGI process or keep the split.
"""

from __future__ import annotations

import os
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

# Use ApiKeyAuth if AI_ACCOUNTS_API_KEY is set; fall back to NoAuth in dev
_api_key = os.environ.get("AI_ACCOUNTS_API_KEY")
if not _api_key:
    # In dev, try to read the same key Flask uses from agented.db settings
    try:
        import sqlite3

        db_path = os.path.join(os.path.dirname(__file__), "..", "agented.db")
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT value FROM settings WHERE key = 'api_key'").fetchone()
            conn.close()
            if row:
                _api_key = row[0]
    except Exception:
        pass

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
