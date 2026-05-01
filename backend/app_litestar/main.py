"""Litestar app factory.

Initially exposes only a /health/liveness route so the skeleton is
verifiable end-to-end. Wave 23 onwards adds real routes.
"""

from __future__ import annotations

from litestar import Litestar

from .auth import provide_caller
from .routes.auth import auth_router
from .routes.health import health_router
from .routes.rbac import rbac_router
from .routes.misc import misc_router
from .routes.utility import utility_router


def create_app() -> Litestar:
    """Build the Litestar application instance."""
    return Litestar(
        route_handlers=[
            health_router,
            rbac_router,
            auth_router,
            utility_router,
            misc_router,
        ],
        dependencies={"caller": provide_caller},
    )
