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
from .routes.admin_misc import admin_misc_router
from .routes.bot_templates import bot_templates_router
from .routes.misc import misc_router
from .routes.payload_transformers import payload_transformers_router
from .routes.quality_ratings import quality_ratings_router
from .routes.scheduler import scheduler_router
from .routes.triggers import triggers_router
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
            admin_misc_router,
            bot_templates_router,
            quality_ratings_router,
            scheduler_router,
            triggers_router,
            payload_transformers_router,
        ],
        dependencies={"caller": provide_caller},
    )
