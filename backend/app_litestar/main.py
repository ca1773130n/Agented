"""Litestar app factory.

Initially exposes only a /health/liveness route so the skeleton is
verifiable end-to-end. Wave 23 onwards adds real routes.
"""

from __future__ import annotations

from litestar import Litestar, get

from .auth import provide_caller
from .routes.auth import auth_router
from .routes.rbac import rbac_router


@get("/health/liveness", sync_to_thread=False)
def liveness() -> dict:
    return {"status": "ok"}


def create_app() -> Litestar:
    """Build the Litestar application instance."""
    return Litestar(
        route_handlers=[liveness, rbac_router, auth_router],
        dependencies={"caller": provide_caller},
    )
