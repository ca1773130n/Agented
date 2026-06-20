"""Per-trigger payload transformer rules (track A, wave 52 — re-enabled).

Originally drafted in wave 50 but shelved because /admin/triggers wasn't
yet on Litestar. Now that wave 52 migrated the trigger namespace, the
nested /admin/triggers/{id}/payload-transformer routes can live here.
"""

from __future__ import annotations

import json
from typing import Any

from litestar import Router, delete, get, put
from litestar.exceptions import HTTPException
from msgspec import Struct, field

from app.db.payload_transformers import (
    delete_transformer,
    get_transformer_by_trigger,
    upsert_transformer,
)

from ..auth import Caller, require_role


class UpsertBody(Struct):
    name: str = "default"
    rules: list = field(default_factory=list)


def _format_row(row: dict) -> dict[str, Any]:
    rules = json.loads(row["rules"]) if isinstance(row["rules"], str) else row["rules"]
    return {
        "id": row["id"],
        "trigger_id": row["trigger_id"],
        "name": row["name"],
        "rules": rules,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@get(
    "/triggers/{trigger_id:str}/payload-transformer",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def get_transformer(trigger_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    row = get_transformer_by_trigger(trigger_id)
    if row is None:
        return {"trigger_id": trigger_id, "name": "default", "rules": []}
    return _format_row(row)


@put(
    "/triggers/{trigger_id:str}/payload-transformer",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def save_transformer(trigger_id: str, data: UpsertBody, authorized: Caller) -> dict[str, Any]:
    del authorized
    rules_json = json.dumps([r if isinstance(r, dict) else r for r in data.rules])
    upsert_transformer(trigger_id=trigger_id, name=data.name, rules_json=rules_json)
    row = get_transformer_by_trigger(trigger_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to upsert transformer")
    return {"message": "Transformer saved", "transformer": _format_row(row)}


@delete(
    "/triggers/{trigger_id:str}/payload-transformer",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def reset_transformer(trigger_id: str, authorized: Caller) -> dict[str, str]:
    del authorized
    deleted = delete_transformer(trigger_id)
    if not deleted:
        return {"message": "No transformer found; nothing to reset"}
    return {"message": "Transformer reset"}


payload_transformers_router = Router(
    path="/admin",
    route_handlers=[get_transformer, save_transformer, reset_transformer],
)
