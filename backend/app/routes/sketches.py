"""Sketch management API endpoints."""

import json
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.sketches import (
    count_sketches,
    delete_sketch,
    get_all_sketches,
    get_sketch,
    update_sketch,
)
from ..db.sketches import (
    create_sketch as db_create_sketch,
)
from ..services.sketch_execution_service import execute_sketch, find_team_super_agent
from ..models.common import PaginationQuery
from ..models.sketch import CreateSketchRequest, UpdateSketchRequest

tag = Tag(name="sketches", description="Sketch management operations")
sketches_bp = APIBlueprint("sketches", __name__, url_prefix="/admin/sketches", abp_tags=[tag])


class SketchPath(BaseModel):
    sketch_id: str = Field(..., description="Sketch ID")


@sketches_bp.get("/")
def list_sketches(query: PaginationQuery):
    """List all sketches with optional filters."""
    status = request.args.get("status")
    project_id = request.args.get("project_id")
    sketches = get_all_sketches(
        status=status, project_id=project_id, limit=query.limit, offset=query.offset or 0
    )
    total_count = count_sketches(status=status, project_id=project_id)
    return {"sketches": sketches, "total_count": total_count}, HTTPStatus.OK


@sketches_bp.post("/")
def create_sketch(body: CreateSketchRequest):
    """Create a new sketch."""
    sketch_id = db_create_sketch(
        title=body.title,
        content=body.content or "",
        project_id=body.project_id,
    )
    if not sketch_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to create sketch", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    return {"message": "Sketch created", "sketch_id": sketch_id}, HTTPStatus.CREATED


@sketches_bp.get("/<sketch_id>")
def get_sketch_endpoint(path: SketchPath):
    """Get a single sketch by ID."""
    sketch = get_sketch(path.sketch_id)
    if not sketch:
        return error_response("NOT_FOUND", "Sketch not found", HTTPStatus.NOT_FOUND)
    return sketch, HTTPStatus.OK


@sketches_bp.put("/<sketch_id>")
def update_sketch_endpoint(path: SketchPath, body: UpdateSketchRequest):
    """Update a sketch."""
    kwargs = body.model_dump(exclude_none=True)

    if not update_sketch(path.sketch_id, **kwargs):
        return error_response(
            "NOT_FOUND", "Sketch not found or no changes made", HTTPStatus.NOT_FOUND
        )

    return {"message": "Sketch updated"}, HTTPStatus.OK


@sketches_bp.delete("/<sketch_id>")
def delete_sketch_endpoint(path: SketchPath):
    """Delete a sketch."""
    if not delete_sketch(path.sketch_id):
        return error_response("NOT_FOUND", "Sketch not found", HTTPStatus.NOT_FOUND)
    return {"message": "Sketch deleted"}, HTTPStatus.OK


@sketches_bp.post("/<sketch_id>/classify")
def classify_sketch_endpoint(path: SketchPath):
    """Classify a sketch using hybrid keyword/LLM pipeline."""
    sketch = get_sketch(path.sketch_id)
    if not sketch:
        return error_response("NOT_FOUND", "Sketch not found", HTTPStatus.NOT_FOUND)

    from ..services.sketch_routing_service import SketchRoutingService

    classification = SketchRoutingService.classify(sketch)
    update_sketch(
        path.sketch_id,
        classification_json=json.dumps(classification),
        status="classified",
    )
    return {"message": "Sketch classified", "classification": classification}, HTTPStatus.OK


@sketches_bp.post("/<sketch_id>/route")
def route_sketch_endpoint(path: SketchPath):
    """Route a classified sketch to a target and execute it."""
    sketch_id = path.sketch_id
    sketch = get_sketch(sketch_id)
    if not sketch:
        return {"error": "Sketch not found"}, HTTPStatus.NOT_FOUND

    classification_raw = sketch.get("classification_json")
    if not classification_raw:
        return {"error": "Sketch must be classified first"}, HTTPStatus.BAD_REQUEST

    classification = (
        json.loads(classification_raw)
        if isinstance(classification_raw, str)
        else classification_raw
    )

    from ..services.sketch_routing_service import SketchRoutingService

    # Route with project scoping
    routing = SketchRoutingService.route(classification, project_id=sketch.get("project_id"))

    # Resolve target super agent
    super_agent_id = None
    if routing["target_type"] == "super_agent":
        super_agent_id = routing["target_id"]
    elif routing["target_type"] == "team":
        super_agent_id = find_team_super_agent(routing["target_id"])

    if not super_agent_id:
        update_sketch(sketch_id, status="routed", routing_json=json.dumps(routing))
        return {"routing": routing}, HTTPStatus.OK

    # Execute on super agent session
    session_id = execute_sketch(sketch_id, super_agent_id, sketch["content"])

    # Store session info in routing_json for frontend
    routing["session_id"] = session_id
    routing["super_agent_id"] = super_agent_id
    update_sketch(sketch_id, routing_json=json.dumps(routing))

    return {
        "routing": routing,
        "session_id": session_id,
        "super_agent_id": super_agent_id,
    }, HTTPStatus.OK
