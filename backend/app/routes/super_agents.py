"""SuperAgent CRUD API endpoints."""

import logging
import sqlite3
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

logger = logging.getLogger(__name__)

from ..database import (
    delete_super_agent,
    get_all_super_agents,
    get_super_agent,
    update_super_agent,
)
from ..database import (
    create_super_agent as db_create_super_agent,
)
from ..models.common import PaginationQuery

tag = Tag(name="super-agents", description="SuperAgent management operations")
super_agents_bp = APIBlueprint(
    "super_agents", __name__, url_prefix="/admin/super-agents", abp_tags=[tag]
)


class SuperAgentPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")


# =============================================================================
# SuperAgent endpoints
# =============================================================================


@super_agents_bp.get("/")
def list_super_agents(query: PaginationQuery):
    """List all super agents."""
    from ..db.super_agents import count_all_super_agents

    super_agents = get_all_super_agents(limit=query.limit, offset=query.offset or 0)
    total_count = count_all_super_agents()
    return {"super_agents": super_agents, "total_count": total_count}, HTTPStatus.OK


@super_agents_bp.post("/")
def create_super_agent():
    """Create a new super agent."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    name = data.get("name")
    if not name:
        return error_response("BAD_REQUEST", "name is required", HTTPStatus.BAD_REQUEST)

    try:
        sa_id = db_create_super_agent(
            name=name,
            description=data.get("description"),
            backend_type=data.get("backend_type", "claude"),
            preferred_model=data.get("preferred_model"),
            team_id=data.get("team_id"),
            parent_super_agent_id=data.get("parent_super_agent_id"),
            max_concurrent_sessions=data.get("max_concurrent_sessions", 10),
            config_json=data.get("config_json"),
        )
    except sqlite3.IntegrityError as e:
        logger.error("Integrity error creating super agent: %s", e)
        return error_response(
            "CONFLICT",
            "A super agent with this name or configuration already exists",
            HTTPStatus.CONFLICT,
        )
    except sqlite3.OperationalError as e:
        logger.error("DB error creating super agent: %s", e)
        return error_response(
            "SERVICE_UNAVAILABLE",
            "Database unavailable, please retry",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    if not sa_id:
        return error_response(
            "INTERNAL_SERVER_ERROR",
            "Failed to create super agent — the database insert returned no ID",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    return {"message": "SuperAgent created", "super_agent_id": sa_id}, HTTPStatus.CREATED


@super_agents_bp.get("/<super_agent_id>")
def get_super_agent_endpoint(path: SuperAgentPath):
    """Get a super agent by ID."""
    sa = get_super_agent(path.super_agent_id)
    if not sa:
        return error_response("NOT_FOUND", "SuperAgent not found", HTTPStatus.NOT_FOUND)
    return sa, HTTPStatus.OK


@super_agents_bp.put("/<super_agent_id>")
def update_super_agent_endpoint(path: SuperAgentPath):
    """Update a super agent."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    if not update_super_agent(
        path.super_agent_id,
        name=data.get("name"),
        description=data.get("description"),
        backend_type=data.get("backend_type"),
        preferred_model=data.get("preferred_model"),
        team_id=data.get("team_id"),
        parent_super_agent_id=data.get("parent_super_agent_id"),
        max_concurrent_sessions=data.get("max_concurrent_sessions"),
        enabled=data.get("enabled"),
        config_json=data.get("config_json"),
    ):
        return error_response(
            "NOT_FOUND", "SuperAgent not found or no changes made", HTTPStatus.NOT_FOUND
        )

    return {"message": "SuperAgent updated"}, HTTPStatus.OK


@super_agents_bp.delete("/<super_agent_id>")
def delete_super_agent_endpoint(path: SuperAgentPath):
    """Delete a super agent."""
    if not delete_super_agent(path.super_agent_id):
        return error_response("NOT_FOUND", "SuperAgent not found", HTTPStatus.NOT_FOUND)
    return {"message": "SuperAgent deleted"}, HTTPStatus.OK
