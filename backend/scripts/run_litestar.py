"""Run the Agented Litestar app (track A migration foundation).

Bound to port 20002 by default — sits alongside Flask (:20000) and
the ai-accounts sidecar (:20001) during the route-by-route migration.
Once Flask retires, this app will collapse onto :20000.

Usage:
    AGENTED_LITESTAR_PORT=20002 uv run python scripts/run_litestar.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the backend package importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from app_litestar import create_app  # noqa: E402


def main() -> None:
    port = int(os.environ.get("AGENTED_LITESTAR_PORT", "20002"))
    host = os.environ.get("AGENTED_LITESTAR_HOST", "127.0.0.1")
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
