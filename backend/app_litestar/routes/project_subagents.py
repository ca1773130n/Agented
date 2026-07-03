"""Phase 17-02 — subagent forge-primitive CRUD routes.

Mirrors ``rules_plugins_hooks_commands.py``. Subagent ids are STR (``subag-…``),
unlike rule/hook/command (INT). The ``subagents`` table is DISTINCT from the
legacy ``agents`` table — these routes never touch ``create_agent``.
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import ClientException, HTTPException, NotFoundException

from app.db import errors as db_errors
from app.db.subagents import (
    create_subagent,
    delete_subagent,
    get_subagent,
    list_subagents,
    update_subagent,
)

from ..auth import Caller


@get("/", sync_to_thread=False)
def list_subagents_endpoint(caller: Caller, project_id: Optional[str] = None) -> dict[str, Any]:
    del caller
    rows = list_subagents(project_id)
    return {"subagents": rows, "total_count": len(rows)}


@post("/", sync_to_thread=False)
def create_subagent_endpoint(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    try:
        subagent = create_subagent(
            name=data.get("name", ""),
            content=data.get("content", ""),
            description=data.get("description"),
            enabled=data.get("enabled", 1),
            project_id=data.get("project_id"),
            source_path=data.get("source_path"),
        )
    except db_errors.IntegrityError:
        raise ClientException(detail="Subagent name already exists")
    if not subagent:
        raise HTTPException(status_code=500, detail="Failed to create subagent")
    return {"message": "Subagent created", "subagent": subagent}


@get("/{subagent_id:str}", sync_to_thread=False)
def get_subagent_endpoint(subagent_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    subagent = get_subagent(subagent_id)
    if not subagent:
        raise NotFoundException(detail="Subagent not found")
    return subagent


@put("/{subagent_id:str}", sync_to_thread=False)
def update_subagent_endpoint(subagent_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not update_subagent(
        subagent_id,
        name=data.get("name"),
        description=data.get("description"),
        content=data.get("content"),
        enabled=data.get("enabled"),
        project_id=data.get("project_id"),
        source_path=data.get("source_path"),
    ):
        raise NotFoundException(detail="Subagent not found or no changes made")
    return get_subagent(subagent_id)


@delete("/{subagent_id:str}", status_code=200, sync_to_thread=False)
def delete_subagent_endpoint(subagent_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not delete_subagent(subagent_id):
        raise NotFoundException(detail="Subagent not found")
    return {"message": "Subagent deleted"}


subagents_router = Router(
    path="/admin/subagents",
    route_handlers=[
        list_subagents_endpoint,
        create_subagent_endpoint,
        get_subagent_endpoint,
        update_subagent_endpoint,
        delete_subagent_endpoint,
    ],
)
