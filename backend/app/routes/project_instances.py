"""Project-scoped SA instance API endpoints."""

import logging
import sqlite3
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.project_sa_instances import (
    get_project_sa_instance,
    get_project_sa_instances_for_project,
)
from ..db.projects import get_project
from ..db.super_agents import get_sessions_for_instance, get_super_agent
from ..services.instance_service import InstanceService

logger = logging.getLogger(__name__)

tag = Tag(name="project-instances", description="Project-scoped SA instance operations")
project_instances_bp = APIBlueprint(
    "project_instances", __name__, url_prefix="/admin/projects", abp_tags=[tag]
)


class ProjectPath(BaseModel):
    project_id: str = Field(..., description="Project ID")


class ProjectInstancePath(BaseModel):
    project_id: str = Field(..., description="Project ID")
    instance_id: str = Field(..., description="Instance ID")


# =============================================================================
# Project instance endpoints
# =============================================================================


@project_instances_bp.post("/<project_id>/instances")
def create_instance(path: ProjectPath):
    """Create project-scoped SA instances from a team or single super agent."""
    project = get_project(path.project_id)
    if not project:
        return error_response("NOT_FOUND", "Project not found", HTTPStatus.NOT_FOUND)

    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    team_id = data.get("team_id")
    super_agent_id = data.get("super_agent_id")

    if not team_id and not super_agent_id:
        return error_response(
            "BAD_REQUEST",
            "At least one of team_id or super_agent_id must be provided",
            HTTPStatus.BAD_REQUEST,
        )

    try:
        if team_id:
            result = InstanceService.create_team_instances(path.project_id, team_id)
        else:
            result = InstanceService.create_sa_instance(path.project_id, super_agent_id)
    except sqlite3.IntegrityError:
        return error_response(
            "CONFLICT",
            "Instance already exists for this project and template",
            HTTPStatus.CONFLICT,
        )

    if result is None:
        return error_response(
            "BAD_REQUEST",
            "Failed to create instance (project or template not found)",
            HTTPStatus.BAD_REQUEST,
        )

    return result, HTTPStatus.CREATED


@project_instances_bp.get("/<project_id>/instances")
def list_instances(path: ProjectPath):
    """List all SA instances for a project, with template SA info."""
    instances = get_project_sa_instances_for_project(path.project_id)

    enriched = []
    for inst in instances:
        sa = get_super_agent(inst["template_sa_id"])
        if sa:
            inst["sa_name"] = sa.get("name")
            inst["sa_description"] = sa.get("description")
            inst["sa_backend_type"] = sa.get("backend_type")
        enriched.append(inst)

    return {"instances": enriched}, HTTPStatus.OK


@project_instances_bp.get("/<project_id>/instances/<instance_id>")
def get_instance(path: ProjectInstancePath):
    """Get a single project SA instance with template SA info and active sessions."""
    instance = get_project_sa_instance(path.instance_id)
    if not instance:
        return error_response("NOT_FOUND", "Instance not found", HTTPStatus.NOT_FOUND)

    if instance["project_id"] != path.project_id:
        return error_response(
            "NOT_FOUND", "Instance not found in this project", HTTPStatus.NOT_FOUND
        )

    # Enrich with template SA info
    sa = get_super_agent(instance["template_sa_id"])
    if sa:
        instance["sa_name"] = sa.get("name")
        instance["sa_description"] = sa.get("description")
        instance["sa_backend_type"] = sa.get("backend_type")

    # Include active sessions
    sessions = get_sessions_for_instance(path.instance_id)
    instance["sessions"] = sessions

    return instance, HTTPStatus.OK


@project_instances_bp.delete("/<project_id>/instances/<instance_id>")
def delete_instance(path: ProjectInstancePath):
    """Delete a project SA instance and clean up its worktree and sessions."""
    instance = get_project_sa_instance(path.instance_id)
    if not instance:
        return error_response("NOT_FOUND", "Instance not found", HTTPStatus.NOT_FOUND)

    if instance["project_id"] != path.project_id:
        return error_response(
            "NOT_FOUND", "Instance not found in this project", HTTPStatus.NOT_FOUND
        )

    InstanceService.delete_instance(path.instance_id)
    return {"message": "Instance deleted"}, HTTPStatus.OK
