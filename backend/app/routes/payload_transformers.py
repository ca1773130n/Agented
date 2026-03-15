"""API endpoints for webhook payload transformer rules."""

import json
from http import HTTPStatus
from typing import Any, List

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.payload_transformers import (
    delete_transformer,
    get_transformer_by_trigger,
    upsert_transformer,
)
from ..services.rbac_service import require_role

tag = Tag(name="payload-transformers", description="Per-trigger webhook payload transform rules")
payload_transformers_bp = APIBlueprint(
    "payload_transformers", __name__, url_prefix="/admin", abp_tags=[tag]
)


class TriggerPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID or 'global'")


class TransformRuleItem(BaseModel):
    id: str = Field(..., description="Client-generated rule ID")
    mode: str = Field(..., description="Transform mode: jsonpath, jq, rename, extract")
    expression: str = Field(..., description="Source expression or field path")
    output_key: str = Field(..., description="Output field name in transformed payload")
    description: str = Field(default="", description="Human-readable rule description")


class UpsertTransformerBody(BaseModel):
    name: str = Field(default="default", description="Transformer name")
    rules: List[Any] = Field(default_factory=list, description="Array of transform rules")


@payload_transformers_bp.get("/triggers/<trigger_id>/payload-transformer")
@require_role("viewer", "operator", "editor", "admin")
def get_transformer(path: TriggerPath):
    """Return the payload transformer for a trigger (or 'global')."""
    row = get_transformer_by_trigger(path.trigger_id)
    if row is None:
        return {
            "trigger_id": path.trigger_id,
            "name": "default",
            "rules": [],
        }, HTTPStatus.OK
    rules = json.loads(row["rules"]) if isinstance(row["rules"], str) else row["rules"]
    return {
        "id": row["id"],
        "trigger_id": row["trigger_id"],
        "name": row["name"],
        "rules": rules,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }, HTTPStatus.OK


@payload_transformers_bp.put("/triggers/<trigger_id>/payload-transformer")
@require_role("editor", "admin")
def save_transformer(path: TriggerPath, body: UpsertTransformerBody):
    """Upsert the payload transformer for a trigger."""
    rules_json = json.dumps([r if isinstance(r, dict) else r for r in body.rules])
    row_id = upsert_transformer(
        trigger_id=path.trigger_id,
        name=body.name,
        rules_json=rules_json,
    )
    row = get_transformer_by_trigger(path.trigger_id)
    if row is None:
        return error_response(
            "INTERNAL_ERROR", "Failed to upsert transformer", HTTPStatus.INTERNAL_SERVER_ERROR
        )
    rules = json.loads(row["rules"]) if isinstance(row["rules"], str) else row["rules"]
    return {
        "message": "Transformer saved",
        "transformer": {
            "id": row["id"],
            "trigger_id": row["trigger_id"],
            "name": row["name"],
            "rules": rules,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
    }, HTTPStatus.OK


@payload_transformers_bp.delete("/triggers/<trigger_id>/payload-transformer")
@require_role("editor", "admin")
def reset_transformer(path: TriggerPath):
    """Delete (reset) the payload transformer for a trigger."""
    deleted = delete_transformer(path.trigger_id)
    if not deleted:
        return {"message": "No transformer found; nothing to reset"}, HTTPStatus.OK
    return {"message": "Transformer reset"}, HTTPStatus.OK
