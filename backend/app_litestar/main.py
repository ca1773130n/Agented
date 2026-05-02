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
from .routes.agents_and_tracing import agents_router, tracing_router
from .routes.bot_templates import bot_templates_router
from .routes.budgets import budgets_router
from .routes.misc import misc_router
from .routes.mcp_servers import mcp_servers_router, project_mcp_router
from .routes.payload_transformers import payload_transformers_router
from .routes.product_owner import product_owner_router
from .routes.projects import projects_router
from .routes.quality_ratings import quality_ratings_router
from .routes.rules_plugins_hooks_commands import (
    commands_router,
    hooks_router,
    plugins_router,
    rules_router,
)
from .routes.scheduler import scheduler_router
from .routes.skills import (
    skill_conversations_router,
    skill_sets_router,
    skills_router,
)
from .routes.teams import teams_router
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
            budgets_router,
            quality_ratings_router,
            scheduler_router,
            triggers_router,
            payload_transformers_router,
            teams_router,
            projects_router,
            product_owner_router,
            mcp_servers_router,
            project_mcp_router,
            skill_conversations_router,
            skills_router,
            skill_sets_router,
            agents_router,
            tracing_router,
            rules_router,
            plugins_router,
            hooks_router,
            commands_router,
        ],
        dependencies={"caller": provide_caller},
    )
