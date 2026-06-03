"""Small shared helpers for Litestar route handlers."""

from __future__ import annotations

from typing import Optional

# Hard ceiling for any client-supplied list `limit`. Mirrors the cap already
# applied ad hoc in executions.py / the audit listers (500/1000). Prevents an
# unbounded-query DoS via `?limit=10000000` (07-routes M2).
MAX_LIST_LIMIT = 500


def clamp_limit(limit: Optional[int], default: int = 100, maximum: int = MAX_LIST_LIMIT) -> int:
    """Clamp a client-supplied list limit into ``[1, maximum]``.

    ``None`` / non-positive falls back to ``default`` (itself clamped)."""
    if limit is None or limit <= 0:
        limit = default
    return max(1, min(limit, maximum))
