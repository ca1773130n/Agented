"""Run the ai-accounts Litestar app alongside Agented's Flask backend.

Listens on 127.0.0.1:20001. The Vite dev server proxies /api/v1/* to this
process; everything else (bots, workflows, teams, etc.) stays on Flask at
port 20000.

This is a transitional arrangement. As more features migrate to
ai-accounts, Flask's responsibilities shrink; post-migration we can either
collapse to one ASGI process or keep the split.
"""

from __future__ import annotations

from pathlib import Path

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

app = create_app(
    AiAccountsConfig(
        env="development",
        storage=SqliteStorage("./ai_accounts.db"),
        vault=EnvKeyVault.from_env(env="development"),
        auth=NoAuth(),
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
