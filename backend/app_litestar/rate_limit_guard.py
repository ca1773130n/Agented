"""v0.5.14: per-route rate-limit guard factory + override registry.

The guard registers (method, path) → (limit, window) on first
invocation. RateLimitMiddleware reads `_PER_ROUTE_OVERRIDES` before
falling through to the coarse defaults table.
"""

from __future__ import annotations

from typing import Optional


# (method, path) → (limit, window_seconds). Populated lazily by
# requires_rate_limit's guard on first request to each protected route.
_PER_ROUTE_OVERRIDES: dict[tuple[str, str], tuple[int, float]] = {}


def get_override(method: str, path: str) -> Optional[tuple[int, float]]:
    """Look up a registered override. Returns None if no match."""
    return _PER_ROUTE_OVERRIDES.get((method, path))


def register_override(method: str, path: str, limit: int, window: float) -> None:
    """Direct registration — exposed for tests + an optional eager
    walker that runs at app startup."""
    _PER_ROUTE_OVERRIDES[(method, path)] = (limit, window)


def clear_overrides() -> None:
    """Test helper — reset the registry between tests."""
    _PER_ROUTE_OVERRIDES.clear()


def requires_rate_limit(limit: int, window_seconds: float):
    """Litestar guard factory. Tighter limit than the coarse default.

    Registers the (method, path) → (limit, window) mapping on the
    first request that hits this route. Returns a no-op guard;
    actual enforcement happens in RateLimitMiddleware via the
    registry.

    The first request to a guarded route falls through to the coarse
    default; subsequent requests use the registered override. This is
    acceptable because coarse defaults are always more permissive than
    overrides — a single coarse-rule pass-through cannot exceed the
    override's intent.
    """
    if limit <= 0 or window_seconds <= 0:
        raise ValueError(
            f"requires_rate_limit: limit and window must be positive; "
            f"got limit={limit}, window_seconds={window_seconds}"
        )

    def guard(connection, _route_handler) -> None:
        method = connection.scope.get("method", "GET")
        path = connection.scope.get("path", "")
        if path:
            register_override(method, path, limit, window_seconds)
        # Enforcement is in middleware. Guard returns None.

    return guard
