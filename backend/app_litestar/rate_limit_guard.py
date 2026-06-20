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

    Returns a guard that also re-registers the override on every
    request (cheap; idempotent). The override is also registered
    EAGERLY at app startup via `eager_register_from_app(app)`, so
    even the very first cold request to a guarded route hits the
    correct limit instead of the coarse default.
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

    # Stamp the guard so the eager startup walker can identify it
    # without resorting to closure introspection.
    guard.__rate_limit__ = (limit, window_seconds)  # type: ignore[attr-defined]
    return guard


def eager_register_from_app(app) -> None:
    """Walk a Litestar app's route table and pre-populate the override
    registry from any handler whose `guards` includes a guard produced
    by `requires_rate_limit`.

    Eliminates the cold-request gap where the coarse default applies
    until the guard registers itself on first hit.
    """
    try:
        routes = app.routes
    except AttributeError:
        return

    for route in routes:
        path = getattr(route, "path", None) or getattr(route, "path_format", None)
        if not path:
            continue
        # Litestar HTTP routes have a `route_handler_map` of {method:
        # (handler, _)} OR `methods` + `route_handler`. Cover both shapes.
        handlers_by_method = {}
        if hasattr(route, "route_handler_map"):
            for method, entry in route.route_handler_map.items():
                handler = entry[0] if isinstance(entry, tuple) else entry
                handlers_by_method[method] = handler
        elif hasattr(route, "route_handler"):
            handler = route.route_handler
            for method in getattr(route, "methods", []) or ["GET"]:
                handlers_by_method[method] = handler

        for method, handler in handlers_by_method.items():
            for guard in getattr(handler, "guards", []) or []:
                meta = getattr(guard, "__rate_limit__", None)
                if meta is not None:
                    limit, window = meta
                    register_override(method, path, limit, window)
