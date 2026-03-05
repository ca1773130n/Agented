"""Bulk operation API endpoints (API-05)."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from ..services.bulk_service import BulkService

tag = Tag(name="bulk", description="Bulk operations (API-05)")
bulk_bp = APIBlueprint("bulk", __name__, url_prefix="/admin/bulk", abp_tags=[tag])


@bulk_bp.post("/agents")
def bulk_agents():
    """Bulk create/update/delete agents."""
    return _handle_bulk("agent")


@bulk_bp.post("/triggers")
def bulk_triggers():
    """Bulk create/update/delete triggers."""
    return _handle_bulk("trigger")


@bulk_bp.post("/plugins")
def bulk_plugins():
    """Bulk create/update/delete plugins."""
    return _handle_bulk("plugin")


@bulk_bp.post("/hooks")
def bulk_hooks():
    """Bulk create/update/delete hooks."""
    return _handle_bulk("hook")


def _handle_bulk(entity_type: str):
    """Shared handler for all bulk endpoints."""
    data = request.get_json()
    if not data:
        return {
            "error": "JSON body required",
            "code": "INVALID_REQUEST",
            "message": "Request body must be valid JSON",
        }, HTTPStatus.BAD_REQUEST

    action = data.get("action")
    items = data.get("items")

    if not action:
        return {
            "error": "action is required",
            "code": "MISSING_FIELD",
            "message": "The 'action' field is required (create, update, or delete)",
        }, HTTPStatus.BAD_REQUEST

    if items is None or not isinstance(items, list):
        return {
            "error": "items must be a list",
            "code": "INVALID_FIELD",
            "message": "The 'items' field must be a JSON array",
        }, HTTPStatus.BAD_REQUEST

    try:
        results = BulkService.process(entity_type, action, items)
    except ValueError as e:
        return {
            "error": str(e),
            "code": "VALIDATION_ERROR",
            "message": str(e),
        }, HTTPStatus.BAD_REQUEST

    succeeded = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])

    return {
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
    }, HTTPStatus.OK
