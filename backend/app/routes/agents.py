"""Agent management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..models.common import PaginationQuery
from ..services.agent_service import AgentService
from ..services.skills_service import SkillsService

tag = Tag(name="agents", description="Agent management operations")
agents_bp = APIBlueprint("agents", __name__, url_prefix="/admin/agents", abp_tags=[tag])


class AgentPath(BaseModel):
    agent_id: str = Field(..., description="Agent ID")


@agents_bp.get("/")
def list_agents(query: PaginationQuery):
    """List all agents with optional pagination."""
    result, status = AgentService.list_agents(limit=query.limit, offset=query.offset or 0)
    return result, status


@agents_bp.post("/")
def create_agent():
    """Create a new agent."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = AgentService.create_agent(data)
    return result, status


@agents_bp.get("/<agent_id>")
def get_agent_detail(path: AgentPath):
    """Get agent details."""
    result, status = AgentService.get_agent_detail(path.agent_id)
    return result, status


@agents_bp.put("/<agent_id>")
def update_agent(path: AgentPath):
    """Update an agent."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = AgentService.update_agent_data(path.agent_id, data)
    return result, status


@agents_bp.delete("/<agent_id>")
def delete_agent(path: AgentPath):
    """Delete an agent."""
    result, status = AgentService.delete_agent_by_id(path.agent_id)
    return result, status


@agents_bp.post("/<agent_id>/run")
def run_agent(path: AgentPath):
    """Execute an agent with an optional message."""
    data = request.get_json() or {}
    message = data.get("message", "")
    result, status = AgentService.run_agent(path.agent_id, message)
    return result, status


@agents_bp.get("/<agent_id>/export")
def export_agent(path: AgentPath):
    """Export an agent to harness plugin format (YAML frontmatter + markdown)."""
    result, status = SkillsService.export_agent_to_harness(path.agent_id)
    return result, status
