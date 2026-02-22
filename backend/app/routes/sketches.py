"""Sketch management API endpoints."""

import json
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..db.sketches import (
    add_sketch,
    delete_sketch,
    get_all_sketches,
    get_sketch,
    update_sketch,
)

tag = Tag(name="sketches", description="Sketch management operations")
sketches_bp = APIBlueprint("sketches", __name__, url_prefix="/admin/sketches", abp_tags=[tag])


class SketchPath(BaseModel):
    sketch_id: str = Field(..., description="Sketch ID")


@sketches_bp.get("/")
def list_sketches():
    """List all sketches with optional filters."""
    status = request.args.get("status")
    project_id = request.args.get("project_id")
    sketches = get_all_sketches(status=status, project_id=project_id)
    return {"sketches": sketches}, HTTPStatus.OK


@sketches_bp.post("/")
def create_sketch():
    """Create a new sketch."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    title = data.get("title")
    if not title:
        return {"error": "title is required"}, HTTPStatus.BAD_REQUEST

    sketch_id = add_sketch(
        title=title,
        content=data.get("content", ""),
        project_id=data.get("project_id"),
    )
    if not sketch_id:
        return {"error": "Failed to create sketch"}, HTTPStatus.INTERNAL_SERVER_ERROR

    return {"message": "Sketch created", "sketch_id": sketch_id}, HTTPStatus.CREATED


@sketches_bp.get("/<sketch_id>")
def get_sketch_endpoint(path: SketchPath):
    """Get a single sketch by ID."""
    sketch = get_sketch(path.sketch_id)
    if not sketch:
        return {"error": "Sketch not found"}, HTTPStatus.NOT_FOUND
    return sketch, HTTPStatus.OK


@sketches_bp.put("/<sketch_id>")
def update_sketch_endpoint(path: SketchPath):
    """Update a sketch."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    allowed_fields = {
        "title",
        "content",
        "project_id",
        "status",
        "classification_json",
        "routing_json",
        "parent_sketch_id",
    }
    kwargs = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_sketch(path.sketch_id, **kwargs):
        return {"error": "Sketch not found or no changes made"}, HTTPStatus.NOT_FOUND

    return {"message": "Sketch updated"}, HTTPStatus.OK


@sketches_bp.delete("/<sketch_id>")
def delete_sketch_endpoint(path: SketchPath):
    """Delete a sketch."""
    if not delete_sketch(path.sketch_id):
        return {"error": "Sketch not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Sketch deleted"}, HTTPStatus.OK


@sketches_bp.post("/<sketch_id>/classify")
def classify_sketch_endpoint(path: SketchPath):
    """Classify a sketch using hybrid keyword/LLM pipeline."""
    sketch = get_sketch(path.sketch_id)
    if not sketch:
        return {"error": "Sketch not found"}, HTTPStatus.NOT_FOUND

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
    """Route a classified sketch to a SuperAgent or team target."""
    sketch = get_sketch(path.sketch_id)
    if not sketch:
        return {"error": "Sketch not found"}, HTTPStatus.NOT_FOUND

    if sketch.get("classification_json") is None:
        return {"error": "Sketch must be classified first"}, HTTPStatus.BAD_REQUEST

    classification = json.loads(sketch["classification_json"])

    from ..services.sketch_routing_service import SketchRoutingService

    routing = SketchRoutingService.route(classification)
    update_sketch(
        path.sketch_id,
        routing_json=json.dumps(routing),
        status="routed",
    )
    return {"message": "Sketch routed", "routing": routing}, HTTPStatus.OK
