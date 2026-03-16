"""Skill sets API endpoints for VisualSkillComposerPage."""

import json
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.skill_sets import (
    create_skill_set,
    delete_skill_set,
    get_all_skill_sets,
    get_skill_set,
    update_skill_set,
)

tag = Tag(name="Skill Sets", description="Skill set compositions for the Visual Skill Composer")
skill_sets_bp = APIBlueprint("skill_sets", __name__, url_prefix="/api/skill-sets", abp_tags=[tag])


class SkillSetPath(BaseModel):
    set_id: str = Field(..., description="Skill set ID")


@skill_sets_bp.get("/")
def list_skill_sets():
    """List all skill sets."""
    skill_sets = get_all_skill_sets()
    return {"skill_sets": skill_sets}, HTTPStatus.OK


@skill_sets_bp.post("/")
def create_skill_set_endpoint():
    """Create a new skill set."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    name = (data.get("name") or "").strip()
    if not name:
        return error_response("BAD_REQUEST", "name is required", HTTPStatus.BAD_REQUEST)

    skill_ids = data.get("skill_ids", [])
    if not isinstance(skill_ids, list):
        return error_response("BAD_REQUEST", "skill_ids must be an array", HTTPStatus.BAD_REQUEST)

    skill_ids_json = json.dumps(skill_ids)
    sset_id = create_skill_set(name=name, skill_ids_json=skill_ids_json)
    if sset_id:
        skill_set = get_skill_set(sset_id)
        return {"message": "Skill set created", "skill_set": skill_set}, HTTPStatus.CREATED
    else:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to create skill set", HTTPStatus.INTERNAL_SERVER_ERROR
        )


@skill_sets_bp.put("/<set_id>")
def update_skill_set_endpoint(path: SkillSetPath):
    """Update an existing skill set."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    skill_set = get_skill_set(path.set_id)
    if not skill_set:
        return error_response("NOT_FOUND", "Skill set not found", HTTPStatus.NOT_FOUND)

    name = data.get("name")
    if name is not None:
        name = name.strip()
        if not name:
            return error_response("BAD_REQUEST", "name cannot be empty", HTTPStatus.BAD_REQUEST)

    skill_ids = data.get("skill_ids")
    skill_ids_json = None
    if skill_ids is not None:
        if not isinstance(skill_ids, list):
            return error_response(
                "BAD_REQUEST", "skill_ids must be an array", HTTPStatus.BAD_REQUEST
            )
        skill_ids_json = json.dumps(skill_ids)

    success = update_skill_set(path.set_id, name=name, skill_ids_json=skill_ids_json)
    if success:
        updated = get_skill_set(path.set_id)
        return {"message": "Skill set updated", "skill_set": updated}, HTTPStatus.OK
    else:
        return error_response("BAD_REQUEST", "No changes made", HTTPStatus.BAD_REQUEST)


@skill_sets_bp.delete("/<set_id>")
def delete_skill_set_endpoint(path: SkillSetPath):
    """Delete a skill set."""
    skill_set = get_skill_set(path.set_id)
    if not skill_set:
        return error_response("NOT_FOUND", "Skill set not found", HTTPStatus.NOT_FOUND)

    success = delete_skill_set(path.set_id)
    if success:
        return {"message": "Skill set deleted"}, HTTPStatus.OK
    else:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to delete skill set", HTTPStatus.INTERNAL_SERVER_ERROR
        )
